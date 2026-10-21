// Local-only bridge: the same provider adapters as the production Worker, no fixtures.
import { collect } from '../services/market-data/worker.mjs';
let input = '';
for await (const chunk of process.stdin) input += chunk;
const history = input ? JSON.parse(input) : [];
const result = await collect({PUBLIC_DISPLAY_APPROVED:'yes', FREE_FEEDS_ENABLED:'yes'}, fetch, Date.now(), history);
process.stdout.write(JSON.stringify(result));
