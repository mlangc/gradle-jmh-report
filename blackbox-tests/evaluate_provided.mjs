// Evaluates a generated provided.js in a fresh vm context and prints the two globals jmh-visualizer reads as JSON.
// Fails if the file doesn't evaluate, or if it defines any global other than these two.
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const EXPECTED = ['providedBenchmarkStore', 'providedBenchmarks'];

const file = process.argv[2];
if (!file) {
  console.error('usage: node evaluate_provided.mjs <provided.js>');
  process.exit(2);
}

const sandbox = {};
try {
  vm.runInNewContext(readFileSync(file, 'utf8'), sandbox, { filename: file });
} catch (e) {
  console.error(`provided.js does not evaluate: ${e}`);
  process.exit(1);
}

const defined = Object.getOwnPropertyNames(sandbox).sort();
if (JSON.stringify(defined) !== JSON.stringify(EXPECTED)) {
  console.error(`provided.js defines globals [${defined}], expected exactly [${EXPECTED}]`);
  process.exit(1);
}

console.log(JSON.stringify({
  providedBenchmarks: sandbox.providedBenchmarks,
  providedBenchmarkStore: sandbox.providedBenchmarkStore,
}));
