const fs = require('fs');
const path = require('path');

const mdPath = 'c:/coding/RecoverAI/WALKTHROUGH.md';
const htmlPath = 'c:/coding/RecoverAI/WALKTHROUGH.html';
const screenshotsDir = 'c:/coding/RecoverAI/docs/screenshots';

let md = fs.readFileSync(mdPath, 'utf8');

// Replace image links with embedded base64 data URIs
md = md.replace(/!\[(.*?)\]\((\.\/docs\/screenshots\/(.*?))\)/g, (match, alt, relPath, filename) => {
  const fullImgPath = path.join(screenshotsDir, filename);
  if (fs.existsSync(fullImgPath)) {
    const b64 = fs.readFileSync(fullImgPath).toString('base64');
    return `<div class="img-card"><img src="data:image/png;base64,${b64}" alt="${alt}" /><p class="caption">${alt}</p></div>`;
  }
  return match;
});

// Basic Markdown to HTML conversion
function convertMarkdown(src) {
  let out = src
    .replace(/^### (.*$)/gim, '<h3>$1</h3>')
    .replace(/^## (.*$)/gim, '<h2>$1</h2>')
    .replace(/^# (.*$)/gim, '<h1>$1</h1>')
    .replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/gim, '<em>$1</em>')
    .replace(/`([^`]+)`/gim, '<code>$1</code>')
    .replace(/```([\s\S]*?)```/gim, '<pre><code>$1</code></pre>')
    .replace(/^\s*-\s+(.*$)/gim, '<li>$1</li>')
    .replace(/(<li>.*<\/li>)/gims, '<ul>$1</ul>')
    .replace(/\n\n+/g, '</p><p>');

  return `<p>${out}</p>`;
}

const bodyHtml = convertMarkdown(md);

const fullHtml = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>RecoverAI — System & Phase 12 Dashboard Walkthrough</title>
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      line-height: 1.6;
      color: #101828;
      background: #F7F8FA;
      margin: 0;
      padding: 40px 20px;
    }
    .container {
      max-width: 960px;
      margin: 0 auto;
      background: #FFFFFF;
      border: 1px solid #E4E7EC;
      border-radius: 12px;
      padding: 48px;
      box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);
    }
    h1 { font-size: 28px; color: #3538CD; margin-top: 0; border-bottom: 2px solid #E4E7EC; padding-bottom: 12px; }
    h2 { font-size: 22px; color: #101828; margin-top: 36px; border-bottom: 1px solid #E4E7EC; padding-bottom: 8px; }
    h3 { font-size: 18px; color: #101828; margin-top: 24px; }
    code { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; background: #F2F4F7; padding: 2px 6px; border-radius: 4px; font-size: 13px; }
    pre { background: #1D2939; color: #F9FAFB; padding: 16px; border-radius: 8px; overflow-x: auto; font-size: 13px; }
    pre code { background: transparent; color: inherit; padding: 0; }
    ul { padding-left: 24px; }
    li { margin-bottom: 6px; }
    .img-card {
      margin: 24px 0;
      border: 1px solid #E4E7EC;
      border-radius: 8px;
      overflow: hidden;
      background: #FFFFFF;
      box-shadow: 0 2px 4px rgba(0,0,0,0.04);
    }
    .img-card img {
      width: 100%;
      height: auto;
      display: block;
    }
    .caption {
      margin: 0;
      padding: 8px 16px;
      background: #F9FAFB;
      border-top: 1px solid #E4E7EC;
      font-size: 12px;
      color: #667085;
      text-align: center;
    }
    @media print {
      body { background: #FFF; padding: 0; }
      .container { border: none; box-shadow: none; padding: 0; max-width: 100%; }
    }
  </style>
</head>
<body>
  <div class="container">
    ${bodyHtml}
  </div>
</body>
</html>`;

fs.writeFileSync(htmlPath, fullHtml);
console.log('Standalone HTML generated at: ' + htmlPath);
