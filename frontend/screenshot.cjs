const { chromium } = require('playwright');
const fs = require('fs');

const DIRS = [
  'C:/Users/kshiv/.gemini/antigravity/brain/81c3090a-3586-4265-a291-8efc623823bb',
  'c:/coding/RecoverAI/docs/screenshots',
];

const SCREENS = [
  { path: '/', name: 'overview' },
  { path: '/transactions', name: 'transactions' },
  { path: '/recovery-queue', name: 'recovery_queue' },
  { path: '/policy-center', name: 'policy_center' },
  { path: '/experiment-lab', name: 'experiment_lab' },
];

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

  // 1. Basic screens
  for (const screen of SCREENS) {
    console.log(`Capturing ${screen.name}...`);
    await page.goto(`http://localhost:3000${screen.path}`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1500);
    for (const dir of DIRS) {
      await page.screenshot({ path: `${dir}/${screen.name}_screenshot.png`, fullPage: true });
    }
  }

  // 2. Transaction Detail (click first row in Transactions)
  console.log('Capturing transaction detail...');
  await page.goto('http://localhost:3000/transactions', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);
  const firstRow = await page.$('tbody tr');
  if (firstRow) {
    await firstRow.click();
    await page.waitForTimeout(1500);
    for (const dir of DIRS) {
      await page.screenshot({ path: `${dir}/transaction_detail_screenshot.png`, fullPage: true });
    }
  }

  // 3. Agent Replay with real full audit trail
  console.log('Capturing agent replay...');
  const resp = await page.request.get('http://localhost:8000/api/transactions?limit=50');
  const data = await resp.json();
  const withVerdict = data.items.find((t) => t.policy_verdict === 'APPROVED') || data.items[0];
  console.log('Using transaction for replay:', withVerdict.id);
  await page.goto(`http://localhost:3000/agent-replay/${withVerdict.id}`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);
  for (const dir of DIRS) {
    await page.screenshot({ path: `${dir}/agent_replay_loaded_screenshot.png`, fullPage: true });
  }

  await browser.close();
  console.log('All screenshots refreshed successfully!');
})();
