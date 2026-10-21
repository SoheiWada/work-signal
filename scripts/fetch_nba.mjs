// Key is read only from the process environment; never from CLI arguments or public files.
import {readFile,writeFile,rename,mkdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {dirname} from 'node:path';
import {collectNba,failedSnapshot} from '../services/nba-data/collector.mjs';
const target=fileURLToPath(new URL('../nba/data.json',import.meta.url));
let previous;try{previous=JSON.parse(await readFile(target,'utf8'))}catch{}
let value,failed=false;
try{value=await collectNba({apiKey:process.env.BALLDONTLIE_API_KEY,...(process.env.NBA_SEASON?{season:Number(process.env.NBA_SEASON)}:{})})}
catch(error){failed=true;value=failedSnapshot(previous,error);console.error(`NBA refresh stopped: ${value.lastError}. No paid endpoint or trial was used.`)}
await mkdir(dirname(target),{recursive:true});await writeFile(target+'.tmp',JSON.stringify(value,null,2)+'\n');await rename(target+'.tmp',target);
if(failed)process.exitCode=1;else console.log(`NBA snapshot saved: ${value.sets.flat().length} final results; ${value.requests} free endpoint requests.`);
