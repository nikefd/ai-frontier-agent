// Carry dependency license/copyright texts into every distributed frontend build.
import { readFileSync, readdirSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const lock = JSON.parse(readFileSync(resolve(root, 'package-lock.json'), 'utf8'));
const notices = new Map();
for (const [location, dependency] of Object.entries(lock.packages)) {
  if (!location || dependency.dev) continue;
  const directory = resolve(root, location);
  const metadata = JSON.parse(readFileSync(resolve(directory, 'package.json'), 'utf8'));
  const licenseFiles = readdirSync(directory).filter(name =>
    /^(?:licen[sc]e|copying|notice)(?:$|\.(?:txt|md|rst)$|-(?:MPL|APACHE)$)/i.test(name));
  if (!licenseFiles.length) throw new Error(`Missing license text: ${metadata.name}`);
  for (const name of licenseFiles.sort()) {
    const text = readFileSync(resolve(directory, name), 'utf8').trim();
    if (!text) throw new Error(`Empty license text: ${metadata.name}/${name}`);
    const packages = notices.get(text) || new Set();
    packages.add(`${metadata.name}@${metadata.version}`);
    notices.set(text, packages);
  }
}
const blocks = [...notices].map(([text, packages]) =>
  `${[...packages].sort().join(', ')}\n\n${text}`);
mkdirSync(resolve(root, 'public'), { recursive: true });
writeFileSync(resolve(root, 'public/THIRD_PARTY_LICENSES.txt'),
  'Frontend third-party license and copyright notices\nGenerated from installed package-lock.json dependencies.\n\n' +
  blocks.join('\n\n' + '='.repeat(72) + '\n\n') + '\n');
console.log(`Collected ${notices.size} distinct third-party license/notice texts.`);
