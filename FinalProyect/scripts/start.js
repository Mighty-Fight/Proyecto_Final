const { exec } = require("child_process");
const path = require("path");

// Corrección: Asegurar rutas absolutas
const serverPath = path.join(__dirname, "..", "server.js"); // Apunta correctamente a la raíz
//const camnewPath = path.join(__dirname, "camnew.py"); // Dentro de scripts/

// Iniciar el servidor Node.js
console.log("Iniciando el servidor...");
const serverProcess = exec(`node ${serverPath}`);

serverProcess.stdout.on("data", (data) => console.log(`SERVER: ${data}`));
serverProcess.stderr.on("data", (data) => console.error(`SERVER ERROR: ${data}`));

// Iniciar el script de Python (camnew.py)
//console.log("Iniciando el reconocimiento de placas con camnew.py...");
//const camnewProcess = exec(`python3 ${camnewPath}`); // Usa 'python' en lugar de 'py' para compatibilidad

//camnewProcess.stdout.on("data", (data) => console.log(`CAMNEW: ${data}`));
//camnewProcess.stderr.on("data", (data) => console.error(`CAMNEW ERROR: ${data}`));
