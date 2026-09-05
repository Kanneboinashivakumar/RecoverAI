const { chromium } = require('playwright');
const { execSync } = require('child_process');

(async () => {
  console.log('--- Testing Backend Disconnection / Error States ---');

  // Stop backend
  console.log('Stopping backend container...');
  execSync('docker compose stop backend', { stdio: 'inherit' });

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

  try {
    console.log('Loading Overview with backend stopped...');
    await page.goto('http://localhost:3000/', { waitUntil: 'load' });
    try {
      await page.waitForSelector('text=Backend Unreachable', { timeout: 8000 });
    } catch (e) {}
    try {
      await page.waitForSelector('text=Failed to load dashboard data', { timeout: 8000 });
    } catch (e) {}

    const errorVisible = await page.locator('text=Failed to load dashboard data').count();
    const systemStatusText = await page.locator('text=Backend Unreachable').count();

    console.log(`✓ Error message displayed: ${errorVisible > 0}`);
    console.log(`✓ TopBar indicator shows "Backend Unreachable": ${systemStatusText > 0}`);

    if (errorVisible > 0 && systemStatusText > 0) {
      console.log('PASSED: Frontend visibly and loudly fails on backend disconnect (no silent/mock data).');
    } else {
      console.error('FAILED: Frontend did not show expected error state.');
    }
  } finally {
    await browser.close();
    console.log('Restarting backend container...');
    execSync('docker compose start backend', { stdio: 'inherit' });
    console.log('Backend restarted.');
  }
})();
