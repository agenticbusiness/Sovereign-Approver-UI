const fs = require('fs');
const path = require('path');
const yaml = require('yaml');
const csv = require('csv-parser');


const VAULT_DIR = path.resolve(__dirname, '..');
const CONFIG_PATH = path.join(VAULT_DIR, 'Matrices', 'parse_request.yaml');
const UI_CONFIG_PATH = path.join(VAULT_DIR, 'Matrices', 'ui_config.yaml');

// Load configurations
const configYaml = fs.readFileSync(CONFIG_PATH, 'utf8');
const config = yaml.parse(configYaml);

const uiConfigYaml = fs.readFileSync(UI_CONFIG_PATH, 'utf8');
const uiConfig = yaml.parse(uiConfigYaml);

const INPUT_DIR = path.join(VAULT_DIR, config.target_folder);
const OUTPUT_DIR = path.join(VAULT_DIR, '_2 Output Data');

if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

const DPI = 150;
const SCALE = DPI / 72;

async function loadMasterCsv(csvPath) {
  return new Promise((resolve, reject) => {
    const results = [];
    if (!fs.existsSync(csvPath)) {
        console.log(`[WARNING] Master CSV not found at ${csvPath}`);
        return resolve(results);
    }
    fs.createReadStream(csvPath)
      .pipe(csv())
      .on('data', (data) => results.push(data))
      .on('end', () => resolve(results))
      .on('error', reject);
  });
}

async function main() {
  console.log('=== Booting LiteParse Engine ===');
  const { LiteParse, searchItems } = await import('@llamaindex/liteparse');  
  const files = fs.readdirSync(INPUT_DIR).filter(f => f.toLowerCase().endsWith('.pdf'));
  if (files.length === 0) {
    console.log(`[INFO] No PDFs found in ${INPUT_DIR}`);
    return;
  }

  const csvBinding = uiConfig.data_bindings[0].source_csv;
  const masterCsv = await loadMasterCsv(path.join(VAULT_DIR, csvBinding));

  const parser = new LiteParse({ outputFormat: 'json', dpi: DPI });

  for (const file of files) {
    const pdfPath = path.join(INPUT_DIR, file);
    console.log(`[ENGINE] Processing ${file}...`);
    
    // Parse to JSON & Screenshot
    const result = await parser.parse(pdfPath);
    const screenshots = await parser.screenshot(pdfPath);

    const baseName = path.basename(file, '.pdf');
    const docOutDir = path.join(OUTPUT_DIR, baseName);
    if (!fs.existsSync(docOutDir)) fs.mkdirSync(docOutDir, { recursive: true });

    // Save screenshots
    for (const shot of screenshots) {
        fs.writeFileSync(path.join(docOutDir, `page_${shot.pageNum}.png`), shot.imageBuffer);
    }

    const payload = {
        filename: file,
        pages: [],
        validation_status: "PENDING_APPROVAL"
    };

    let totalMatches = 0;

    // Process Proxy RAG extraction
    for (const page of result.json?.pages || []) {
        const pageMatches = [];
        for (const target of config.extraction_targets) {
            // Apply Safeguard Regex as Proxy Pointer RAG constraint
            const regex = new RegExp(target.safeguard_regex);
            
            // We use searchItems to find contiguous text, or filter raw items
            const matches = page.textItems.filter(item => regex.test(item.text.trim()));
            
            matches.forEach(m => {
                pageMatches.push({
                    field: target.field,
                    text: m.text,
                    bbox: { x: m.x, y: m.y, width: m.width, height: m.height },
                    pixels: { 
                        left: Math.round(m.x * SCALE), 
                        top: Math.round(m.y * SCALE), 
                        width: Math.round(m.width * SCALE), 
                        height: Math.round(m.height * SCALE) 
                    }
                });
                totalMatches++;
            });
        }
        
        payload.pages.push({
            page_num: page.page,
            matches: pageMatches
        });
    }

    // Image Validator
    if (config.validation.enforce_count_match) {
        // Compare to expected count in CSV
        // (Assuming CSV has a 'Physical Page' column or we just match total file count)
        const expectedCount = masterCsv.length; // Simplified for MVP
        if (totalMatches !== expectedCount) {
            console.log(`[VALIDATION] Count Mismatch! Found: ${totalMatches}, Expected: ${expectedCount}`);
            payload.validation_status = "REQUIRES_MANUAL_REVIEW";
        } else {
            console.log(`[VALIDATION] Bounding Box Count Verified: ${totalMatches}`);
        }
    }

    // Write final parsed spatial JSON payload for UI to ingest
    fs.writeFileSync(path.join(docOutDir, 'parsed_spatial_data.json'), JSON.stringify(payload, null, 2));
    console.log(`[SUCCESS] Extracted ${totalMatches} spatial citations for ${file}`);
  }
}

main().catch(err => {
  console.error('[FATAL]', err);
  process.exit(1);
});
