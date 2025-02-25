const { exec } = require('child_process');

// Iniciar el servidor Node.js
console.log("Iniciando el servidor...");
const serverProcess = exec('node server.js');

serverProcess.stdout.on('data', (data) => console.log(`SERVER: ${data}`));
serverProcess.stderr.on('data', (data) => console.error(`SERVER ERROR: ${data}`));

// Iniciar el script de Python (camnew.py)
console.log("Iniciando el reconocimiento de placas con camnew.py...");
const camnewProcess = exec('py scripts/camnew.py');

camnewProcess.stdout.on('data', (data) => console.log(`CAMNEW: ${data}`));
camnewProcess.stderr.on('data', (data) => console.error(`CAMNEW ERROR: ${data}`));
