// Runs the real launcher and browser setup against an empty, disposable installation.
const {chromium} = require('playwright');
const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');
const {spawn} = require('child_process');
const assert = require('assert/strict');
const project = path.resolve(__dirname, '..');
const [baseZip, addendumZip] = process.argv.slice(2);
if (!baseZip || !addendumZip) throw new Error('Usage: node tests/first_run.cjs <stage2-materials.zip> <packaging-addendum.zip>');
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'cdek-first-run-'));
const install = path.join(temp, 'VS Code СДЭК', 'cdek-assistant');
fs.cpSync(project, install, {recursive:true, filter:source => !path.relative(project,source).split(path.sep).some(part=>['data','__pycache__','node_modules','.git','docs'].includes(part))});
const data = path.join(install,'data');
const port = 18082;
const url = `http://127.0.0.1:${port}`;
let server, output='', browser;
const password = crypto.randomBytes(24).toString('base64url');
const errors=[];
const pause = ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function launch(first) {
  output='';
  server=spawn('python3',['-u',path.join(install,'start.py'),'--no-browser','--port',String(port)],{cwd:temp,stdio:['ignore','pipe','pipe']});
  server.stdout.on('data',b=>{output+=b.toString();});
  server.stderr.on('data',()=>{});
  for(let i=0;i<150;i++) {
    if(server.exitCode!==null) throw new Error('Launcher stopped unexpectedly');
    if(output.includes('Оставьте это окно открытым.')) break;
    await pause(100);
  }
  assert.ok(output.includes(url),'Launcher must print server address');
  if(first) {const match=output.match(/http:\/\/127\.0\.0\.1:\d+\/#setup=[\w-]+/);assert.ok(match,'First launch must offer admin creation');return match[0];}
  assert.ok(!output.includes('#setup='),'Restart must not offer registration once account exists');
  return url;
}
async function stop() {if(server && server.exitCode===null){const ended=new Promise(r=>server.once('exit',r));server.kill('SIGINT');await ended;}}
async function login(page) {
  await page.fill('#username','local-admin');await page.fill('#password',password);await page.locator('#login-form button').click();
  await page.locator('#workspace').waitFor({state:'visible'});
  await page.waitForFunction(()=>document.getElementById('source-count').textContent!=='—');
}
async function upload(page, kind, file, expected) {
  await page.selectOption('#import-kind',kind);await page.setInputFiles('#import-file',file);await page.click('#import-submit');
  await page.waitForFunction(text=>document.getElementById('import-status').textContent.includes(text),expected,{timeout:120000});
}
(async()=>{
  assert.equal(fs.existsSync(data),false,'No preinstalled database/accounts allowed');
  const setupUrl=await launch(true);
  browser=await chromium.launch({executablePath:process.env.CDEK_CHROMIUM || '/usr/bin/chromium',headless:true,args:['--no-sandbox']});
  const page=await browser.newPage({viewport:{width:1440,height:1050}});page.on('pageerror',e=>errors.push(e.message));
  await page.goto(url);await page.locator('#setup-view').waitFor({state:'visible'});
  assert.equal(await page.locator('#setup-submit').isDisabled(),true,'No open registration without launch token');
  await page.goto(setupUrl);await page.locator('#setup-submit:not([disabled])').waitFor();
  assert.equal(await page.evaluate(()=>location.hash),'','Bootstrap token must be removed from address bar');
  await page.fill('#setup-username','local-admin');await page.fill('#setup-password',password);await page.fill('#setup-confirmation',password+'x');
  await page.click('#setup-submit');await page.getByText('Пароли должны совпадать',{exact:false}).waitFor();
  await page.fill('#setup-confirmation',password);await page.click('#setup-submit');
  await page.locator('#login-form').waitFor({state:'visible'});await login(page);
  assert.equal(await page.locator('#source-count').innerText(),'0');
  await page.locator('#empty-database').waitFor({state:'visible'});
  await page.locator('#question-form').waitFor({state:'visible'});
  await page.locator('#import-panel').waitFor({state:'visible'});
  await page.click('#sources-tab');await page.locator('#source-list-empty').waitFor({state:'visible'});await page.click('#show-import');
  await upload(page,'base',{name:'bad.zip',mimeType:'application/zip',buffer:Buffer.from('not a zip')},'Не удалось прочитать ZIP');
  assert.equal(await page.locator('#source-count').innerText(),'0');
  await upload(page,'addendum',path.resolve(addendumZip),'Сначала импортируйте основной');
  await upload(page,'base',path.resolve(baseZip),'SHA256 проверен для 315 файлов');
  await page.waitForFunction(()=>document.getElementById('source-count').textContent==='206');
  assert.equal(await page.locator('#approved-count').innerText(),'0');
  await page.locator('.source-row').first().waitFor();
  await upload(page,'addendum',path.resolve(addendumZip),'SHA256 проверен для 11 файлов');
  await page.fill('#review-query','духи');await page.locator('#review-search button').click();
  await page.locator('#review-results .citation').first().waitFor();
  assert.ok((await page.locator('#review-results').innerText()).includes('Только для проверки'));
  await page.fill('#source-filter','395');await page.locator('#source-list button').first().click();
  await page.locator('#source-detail').getByText('История версий источника',{exact:true}).waitFor();
  assert.ok((await page.locator('#source-detail').innerText()).includes('packaging-addendum'));
  await page.click('[data-tab=assistant]');await page.fill('#question','Духи, несколько флаконов: какие сведения нужно уточнить?');await page.click('#ask-button');
  await page.getByRole('heading',{name:'Нужна проверка источников'}).waitFor();
  fs.mkdirSync(path.join(project,'docs'),{recursive:true});
  await page.screenshot({path:path.join(project,'docs','after-login.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.setViewportSize({width:1440,height:1050});
  await page.click('#logout');await page.locator('#login-form').waitFor({state:'visible'});
  await stop();await launch(false);
  await page.goto(url);await page.locator('#login-form button:not([disabled])').waitFor();await login(page);
  await page.waitForFunction(()=>document.getElementById('source-count').textContent==='206');
  await page.click('#sources-tab');await page.fill('#review-query','упаковка');await page.locator('#review-search button').click();
  await page.locator('#review-results .citation').first().waitFor();
  await page.click('#logout');await page.locator('#login-form').waitFor({state:'visible'});await login(page);
  assert.deepEqual(errors,[]);
  console.log('PASS: clean copied installation in a Unicode/space path; real launcher; browser admin creation with user-chosen password; empty-base guidance; invalid ZIP and addendum-before-base errors; base and addendum ZIP uploads; 206 unapproved sources; workspace and product-query form; admin document list/search/version view; logout; server restart; login and persisted document search; mobile width; no page errors.');
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();await stop();fs.rmSync(temp,{recursive:true,force:true});});
