const { spawn } = require('child_process');

// Función para ejecutar un proceso
function startProcess(command, args, name) {
  const process = spawn(command, args, { stdio: 'inherit' });

  process.on('error', (err) => {
    console.error(`[${name}] Error: ${err.message}`);
  });

  process.on('exit', (code) => {
    if (code !== 0) {
      console.error(`[${name}] Salió con código ${code}. Reiniciando...`);
      startProcess(command, args, name); // Reiniciar el proceso
    } else {
      console.log(`[${name}] Finalizó correctamente.`);
    }
  });
}

// Iniciar server.js
startProcess('node', ['server.js'], 'Node.js Server');

// Iniciar camnew.py
startProcess('python3', ['camnew.py'], 'Python Plate Detection');

// Iniciar mjpeg_server.py
//startProcess('python3', ['mjpeg_server.py'], 'Python MJPEG Server');

