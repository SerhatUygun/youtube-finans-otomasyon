// Günlük otomasyon girişi (tools/daily_run.py -> npx remotion render src/auto/index.ts ...).
import {registerRoot} from 'remotion';
import {AutoRoot} from './Root';

registerRoot(AutoRoot);
