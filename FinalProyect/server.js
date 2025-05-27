const express = require('express');
const http = require('http');
const socketIo = require('socket.io');
const bodyParser = require('body-parser');
const session = require('express-session');
const path = require('path');
const authRoutes = require('./routes/authRoutes');
const plateRoutes = require('./routes/plateRoutes');
const { isAuthenticated } = require('./middleware/authMiddleware');
const db = require('./config/db');

// 1) Se importa dotenv y moment-timezone
require('dotenv').config();
const moment = require('moment-timezone'); // <--- AÑADIDO

const app = express();
const server = http.createServer(app);
const io = socketIo(server);

app.use(session({
    secret: 'mi_secreto_super_seguro',
    resave: false,
    saveUninitialized: true
}));

app.use(express.urlencoded({ extended: true }));
app.use(bodyParser.json());

// Rutas de autenticación y placas
app.use('/', authRoutes);
app.use('/plates', plateRoutes);

// Ruta protegida para acceder al panel de control
app.get('/dashboard', isAuthenticated, (req, res) => {
    console.log(`Usuario autenticado: ${req.session.user.username}`);
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.get("/", (req, res) => {
    res.sendFile(path.join(__dirname, "public", "principal.html"));
});

app.use(express.static(path.join(__dirname, 'public')));

// Ruta para obtener información del usuario autenticado
app.get("/user-info", (req, res) => {
    if (!req.session.user) {
        return res.status(401).json({ error: "No autorizado" });
    }
    res.json({ username: req.session.user.username });
});

// Comunicación con Socket.IO
let placaStatus = 'No se ha detectado ninguna placa aún';
let lastPlate = ''; // Última placa registrada
let lastPlateImageBase64 = ''; // Aquí se guardará la imagen OCR en Base64

io.on('connection', (socket) => {
    console.log('Usuario conectado');
    
    // 2) Forzamos la hora a Bogotá en vez de usar new Date()
    const fechaBogota = moment().tz("America/Bogota").format("YYYY-MM-DD HH:mm:ss");
    socket.emit('updatePlaca', { placa: placaStatus, timestamp: fechaBogota });

    socket.on('disconnect', () => {
        console.log('Usuario desconectado');
    });
});

// Recibir placas desde camnew.py
app.post('/update', (req, res) => {
    const { placa, frame } = req.body;

    // 3) Generamos la hora de Bogotá
    const fechaBogota = moment().tz("America/Bogota").format("YYYY-MM-DD HH:mm:ss");

    if (!placa || placa === "No se ha detectado ninguna placa aún") {
        console.warn('Placa no válida recibida.');
        return res.json({ success: false, message: "Placa no válida" });
    }

    if (placa === lastPlate) {
        console.log(`Placa repetida (${placa}), no se inserta de nuevo.`);
        return res.json({ success: false, message: "Placa repetida" });
    }

    lastPlate = placa;
    console.log(`Nueva placa recibida: ${placa}`);
    placaStatus = placa;

    // Guardar la imagen OCR en Base64, si se envía
    if (frame) {
        lastPlateImageBase64 = frame;
    }

    // 4) Emitimos la hora de Bogotá al front
    io.emit('updatePlaca', { placa, timestamp: fechaBogota, frame });

    // 5) Insertar la placa en la base de datos con hora Bogotá
    db.query('INSERT INTO placas (placa, timestamp) VALUES (?, ?)', [placa, fechaBogota], (err) => {
        if (err) {
            console.error('Error al insertar en la base de datos:', err.message);
            return res.status(500).json({ success: false, error: 'Error interno.' });
        } else {
            console.log(`Placa "${placa}" guardada en la base de datos.`);
            return res.json({ success: true, placa });
        }
    });
});

// Endpoint para servir la imagen OCR convertida a imagen JPEG
app.get('/last-ocr-image', (req, res) => {
    if (!lastPlateImageBase64) {
        return res.status(404).send('No hay imagen de placa');
    }
    // Convertir la cadena Base64 a Buffer
    const imgBuffer = Buffer.from(lastPlateImageBase64, 'base64');
    res.writeHead(200, {
        'Content-Type': 'image/jpeg',
        'Content-Length': imgBuffer.length
    });
    return res.end(imgBuffer);
});

// Verificar si la placa ya está registrada en la base de datos
app.get('/verificar-vehiculo', (req, res) => {
    const { placa } = req.query;
  
    if (!placa) {
      return res.status(400).json({ error: 'La placa es necesaria' });
    }
  
    const query = 'SELECT * FROM vehiculos WHERE placa = ?';
    db.query(query, [placa], (err, result) => {
      if (err) {
        console.error('Error al verificar la placa:', err.message);
        return res.status(500).json({ error: 'Error interno' });
      }
  
      if (result.length > 0) {
        // Si la placa existe, devolver la información del vehículo
        res.json(result[0]);
      } else {
        // Si no existe, devolver un mensaje para el cliente
        res.status(404).json({ error: 'Vehículo no registrado' });
      }
    });
  });

// Guardar el registro de un vehículo y su servicio
app.post('/guardar-registro', (req, res) => {   
    const { placa, tipo_carro, servicios, precio_total, operarios, nombre_dueno, telefono } = req.body;

    const vehiculosQuery = 'SELECT * FROM vehiculos WHERE placa = ?';
    db.query(vehiculosQuery, [placa], (err, result) => {
        if (err) {
            console.error('Error al verificar la placa:', err.message);
            return res.status(500).json({ success: false, message: "Error al verificar la placa" });
        }

        const continuarConPlanilla = () => {
            // Buscar tiempo estimado
            const obtenerTiempoEstimado = 'SELECT tiempo_estimado FROM servicios WHERE nombre = ?';
            db.query(obtenerTiempoEstimado, [servicios], (err, resultadoTiempo) => {
                if (err || resultadoTiempo.length === 0) {
                    console.error('Error al obtener tiempo estimado:', err?.message);
                    return res.status(500).json({ success: false, message: "Error al consultar tiempo estimado" });
                }

                const tiempo_estimado = resultadoTiempo[0].tiempo_estimado;
                const fechaActual = moment().tz('America/Bogota').format('YYYY-MM-DD');

                const insertPlanilla = `
                    INSERT INTO planilla (placa, tipo_carro, servicios, precio_total, operarios, fecha, estado, tiempo_estimado)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                `;
                db.query(insertPlanilla, [placa, tipo_carro, servicios, precio_total, operarios, fechaActual, 'en_espera', tiempo_estimado], (err) => {
                    if (err) {
                        console.error('Error al guardar en planilla:', err.message);
                        return res.status(500).json({ success: false, message: "Error al guardar en planilla" });
                    }
                    
                    io.emit('nuevoRegistroPlanilla', {
                        placa,
                        tipo_carro,
                        servicios,
                        precio_total,
                        operarios,
                        fecha: fechaActual,
                        estado: 'en_espera'
                    });
                    res.json({ success: true, message: "Registro guardado correctamente" });
                    
                });
            });
        };

        if (result.length === 0) {
            const insertVehiculo = `
                INSERT INTO vehiculos (placa, nombre_dueno, telefono)
                VALUES (?, ?, ?)
            `;
            db.query(insertVehiculo, [placa, nombre_dueno, telefono], (err) => {
                if (err) {
                    console.error('Error al guardar el vehículo:', err.message);
                    return res.status(500).json({ success: false, message: "Error al guardar el vehículo" });
                }
                continuarConPlanilla(); // solo después de insertar correctamente
            });
        } else {
            continuarConPlanilla(); // si ya existe el vehículo
        }
    });
});


// Endpoint para atender o finalizar un vehículo
app.post('/atender-detener', (req, res) => {
    const { placa, nuevoEstado } = req.body;

    if (!placa || !nuevoEstado) {
        return res.status(400).json({ success: false, message: "Faltan datos" });
    }

    if (nuevoEstado === 'en_atencion') {
        const fechaInicio = moment().tz('America/Bogota').format('YYYY-MM-DD HH:mm:ss');
        const updateQuery = 'UPDATE planilla SET estado = ?, inicio_servicio = ? WHERE placa = ?';
        const updateParams = [nuevoEstado, fechaInicio, placa];

        db.query(updateQuery, updateParams, (err, result) => {
            if (err) {
                console.error('❌ Error al actualizar a en_atencion:', err);
                return res.status(500).json({ success: false });
            }

            if (result.affectedRows === 0) {
                return res.status(400).json({ success: false, message: 'No se encontró la placa' });
            }

            io.emit('estadoCambiado', { placa, estado: nuevoEstado });

            // 🔔 Enviar mensaje por WhatsApp
            const queryTelefono = 'SELECT telefono FROM vehiculos WHERE placa = ?';
            db.query(queryTelefono, [placa], (err, result) => {
                if (!err && result.length > 0) {
                    const numero = result[0].telefono;
                    const mensaje = `🚗 Tu vehículo con placa ${placa} ha cambiado de estado a *${nuevoEstado}*. Gracias por confiar en LubriWash.`;
                    const payload = { numero, mensaje };

                    fetch('http://localhost:5000/enviar', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    })
                    .then(res => res.json())
                    .then(data => console.log("📩 Mensaje enviado:", data))
                    .catch(err => console.error("❌ Error al enviar mensaje WhatsApp:", err));
                }
            });

            return res.json({ success: true });
        });

    } else if (nuevoEstado === 'finalizado') {
        const horaFinal = moment().tz('America/Bogota').format('YYYY-MM-DD HH:mm:ss');

        const queryInfo = 'SELECT tiempo_estimado, inicio_servicio FROM planilla WHERE placa = ? AND fecha = CURDATE()';
        db.query(queryInfo, [placa], (err, resultados) => {
            if (err || resultados.length === 0) {
                console.error("❌ Error consultando datos para rendimiento:", err?.message);
                return res.status(500).json({ success: false });
            }

            const { tiempo_estimado, inicio_servicio } = resultados[0];
            const tiempoReal = moment(horaFinal).diff(moment(inicio_servicio), 'minutes');

            let rendimiento;
            if (tiempoReal <= tiempo_estimado * 0.8) rendimiento = 'Más rápido';
            else if (tiempoReal <= tiempo_estimado * 1.1) rendimiento = 'Puntual';
            else if (tiempoReal <= tiempo_estimado * 1.5) rendimiento = 'Lento';
            else rendimiento = 'Muy lento';

            const updateQuery = `
                UPDATE planilla 
                SET estado = ?, hora_finalizacion = ?, rendimiento = ?
                WHERE placa = ?
            `;
            const updateParams = [nuevoEstado, horaFinal, rendimiento, placa];

            db.query(updateQuery, updateParams, (err, result) => {
                if (err) {
                    console.error('❌ Error al finalizar servicio:', err.message);
                    return res.status(500).json({ success: false });
                }

                if (result.affectedRows === 0) {
                    return res.status(400).json({ success: false, message: 'No se encontró la placa' });
                }

                io.emit('estadoCambiado', { placa, estado: nuevoEstado });

                // 🔔 Enviar mensaje por WhatsApp
                const queryTelefono = 'SELECT telefono FROM vehiculos WHERE placa = ?';
                db.query(queryTelefono, [placa], (err, result) => {
                    if (!err && result.length > 0) {
                        const numero = result[0].telefono;
                        const mensaje = `🚗 Tu vehículo con placa ${placa} ha cambiado de estado a *${nuevoEstado}*. Gracias por confiar en LubriWash.`;
                        const payload = { numero, mensaje };

                        fetch('http://localhost:5000/enviar', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(payload)
                        })
                        .then(res => res.json())
                        .then(data => console.log("📩 Mensaje enviado:", data))
                        .catch(err => console.error("❌ Error al enviar mensaje WhatsApp:", err));
                    }
                });

                return res.json({ success: true });
            });
        });

    } else {
        const updateQuery = 'UPDATE planilla SET estado = ? WHERE placa = ?';
        const updateParams = [nuevoEstado, placa];

        db.query(updateQuery, updateParams, (err, result) => {
            if (err) {
                console.error('Error al actualizar el estado:', err);
                return res.status(500).json({ success: false });
            }

            if (result.affectedRows === 0) {
                return res.status(400).json({ success: false, message: 'El vehículo no existe o no se puede actualizar' });
            }

            io.emit('estadoCambiado', { placa, estado: nuevoEstado });

            // 🔔 Enviar mensaje por WhatsApp
            const queryTelefono = 'SELECT telefono FROM vehiculos WHERE placa = ?';
            db.query(queryTelefono, [placa], (err, result) => {
                if (!err && result.length > 0) {
                    const numero = result[0].telefono;
                    const mensaje = `🚗 Tu vehículo con placa ${placa} ha cambiado de estado a *${nuevoEstado}*. Gracias por confiar en LubriWash.`;
                    const payload = { numero, mensaje };

                    fetch('http://localhost:5000/enviar', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    })
                    .then(res => res.json())
                    .then(data => console.log("📩 Mensaje enviado:", data))
                    .catch(err => console.error("❌ Error al enviar mensaje WhatsApp:", err));
                }
            });

            return res.json({ success: true });
        });
    }
});




// Obtener registros de placas
app.get('/planilla', (req, res) => {
    const { fecha } = req.query;  // Toma la fecha desde la solicitud
    let sql = 'SELECT placa, tipo_carro, servicios, precio_total, operarios, fecha, estado, rendimiento FROM planilla';
    let params = [];

    // Si se pasa una fecha, usarla para la consulta
    if (fecha) {
        sql += ' WHERE fecha = ?';
        params.push(fecha);
    } else {
        // 7) También reemplazamos aquí la fecha actual
        const fechaActual = moment().tz('America/Bogota').format('YYYY-MM-DD');
        sql += ' WHERE fecha = ?';
        params.push(fechaActual);
    }

    db.query(sql, params, (err, results) => {
        if (err) {
            console.error('Error al obtener los registros de planilla:', err);
            return res.status(500).json({ error: 'Error al obtener los registros' });
        }
        res.json(results);
    });
});

// Obtener registros de placas
app.get('/get-plates', (req, res) => {
    let { plate, startDate, endDate } = req.query;
    let sql = 'SELECT id, placa, timestamp FROM placas';
    let params = [];

    if (plate || startDate || endDate) {
        let conditions = [];
        if (plate) {
            conditions.push('placa LIKE ?');
            params.push(`%${plate}%`);
        }
        if (startDate) {
            conditions.push('timestamp >= ?');
            params.push(startDate);
        }
        if (endDate) {
            conditions.push('timestamp <= ?');
            params.push(endDate);
        }
        if (conditions.length > 0) {
            sql += ' WHERE ' + conditions.join(' AND ');
        }
    } else {
        // Esto sigue usando CURDATE() en MySQL,
        // si deseas forzar hora Bogotá también puedes cambiarlo por 
        // "DATE(timestamp) = DATE(CONVERT_TZ(NOW(),'UTC','America/Bogota'))" 
        // o seguir usándolo así si te funciona bien.
        sql += ' WHERE DATE(timestamp) = CURDATE()';
    }

    db.query(sql, params, (err, results) => {
        if (err) {
            console.error('Error en /get-plates:', err);
            return res.status(500).json({ error: 'Error interno del servidor' });
        }
        return res.json(results);
    });
});

app.get('/cajero', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'cajero.html'));
});

app.get('/vista_salon', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'vista_salon.html'));
});

app.get("/index.html", isAuthenticated, (req, res) => {
    res.redirect("/dashboard");
});

app.get('/verificar-telefono', (req, res) => {
    const { telefono } = req.query;

    if (!telefono) {
        return res.status(400).json({ success: false, message: 'Falta el número de teléfono' });
    }

    const queryVehiculo = 'SELECT * FROM vehiculos WHERE telefono = ?';
    db.query(queryVehiculo, [telefono], (err, vehiculoResult) => {
        if (err) {
            console.error('Error al buscar el teléfono:', err.message);
            return res.status(500).json({ success: false, message: 'Error interno' });
        }

        if (vehiculoResult.length === 0) {
            return res.json({ success: true, existe: false });
        }

        const vehiculo = vehiculoResult[0];
        const placa = vehiculo.placa;
        const fechaActual = moment().tz('America/Bogota').format('YYYY-MM-DD');

        const queryPlanilla = 'SELECT estado, precio_total FROM planilla WHERE placa = ? AND fecha = ? ORDER BY id DESC LIMIT 1';
        db.query(queryPlanilla, [placa, fechaActual], (err, planillaResult) => {
            if (err) {
                console.error('Error al buscar estado en planilla:', err.message);
                return res.status(500).json({ success: false, message: 'Error interno buscando estado' });
            }

            if (planillaResult.length > 0) {
                return res.json({
                    success: true,
                    existe: true,
                    datos: vehiculo,
                    placa: placa,
                    estado: planillaResult[0].estado,
                    precio_total: planillaResult[0].precio_total
                });
            } else {
                return res.json({
                    success: true,
                    existe: true,
                    datos: vehiculo,
                    placa: placa,
                    estado: null,
                    precio_total: null // No tiene registro en planilla
                });
            }
        });
    });
});


app.post('/submit-feedback', (req, res) => {
    const { comentario } = req.body;

    if (!comentario) {
        return res.status(400).json({ success: false, message: "Comentario vacío" });
    }

    const sql = 'INSERT INTO feedbacks (comentario) VALUES (?)';
    
    db.query(sql, [comentario], (err, result) => {
        if (err) {
            console.error('Error al guardar el feedback:', err);
            return res.status(500).json({ success: false, error: 'Error interno.' });
        }
        console.log('Feedback guardado correctamente.');
        return res.json({ success: true, message: "Gracias por tu opinión!" });
    });
});

app.get('/servicios', (req, res) => {
    const sql = 'SELECT nombre, categoria, precio FROM servicios ORDER BY categoria, nombre';
    db.query(sql, (err, results) => {
      if (err) {
        console.error('Error al obtener servicios:', err);
        return res.status(500).json({ error: 'Error al consultar servicios' });
      }
      res.json(results);
    });
  });
  
app.get('/grupos', (req, res) => {
    const sql = 'SELECT id, nombre FROM grupos ORDER BY nombre';
    db.query(sql, (err, results) => {
        if (err) {
        console.error('Error al obtener grupos:', err);
        return res.status(500).json({ error: 'Error al consultar grupos' });
        }
        res.json(results);
    });
});

function consultarTrabajosDeHoyPorGrupo() {
    const hoy = moment().tz('America/Bogota').format('YYYY-MM-DD');
    const sql = `
        SELECT operarios, servicios, placa 
        FROM planilla 
        WHERE fecha = ? 
        ORDER BY operarios
    `;

    db.query(sql, [hoy], (err, results) => {
        if (err) {
            console.error('❌ Error al consultar trabajos de hoy:', err.message);
            return;
        }

        if (results.length === 0) {
            console.log('📭 No hay trabajos asignados para hoy.');
            return;
        }

        const trabajosPorGrupo = {};

        results.forEach(row => {
            const grupo = row.operarios;
            if (!trabajosPorGrupo[grupo]) {
                trabajosPorGrupo[grupo] = [];
            }
            trabajosPorGrupo[grupo].push({
                placa: row.placa,
                servicio: row.servicios
            });
        });

        console.log('📋 Trabajos asignados para hoy:');
        for (const grupo in trabajosPorGrupo) {
            console.log(`\n🔧 ${grupo}:`);
            trabajosPorGrupo[grupo].forEach(trabajo => {
                console.log(`   🚗 Placa: ${trabajo.placa} | Servicio: ${trabajo.servicio}`);
            });
        }
    });
}

app.get('/tiempos-restantes', (req, res) => {
    const sql = `
        SELECT 
            operarios,
            estado,
            tiempo_estimado,
            inicio_servicio,
            CASE 
                WHEN estado = 'en_atencion' AND inicio_servicio IS NOT NULL THEN 
                    GREATEST(0, tiempo_estimado - TIMESTAMPDIFF(MINUTE, inicio_servicio, CONVERT_TZ(NOW(), 'UTC', 'America/Bogota')))
                WHEN estado = 'en_espera' THEN 
                    tiempo_estimado
                ELSE 0
            END AS minutos_restantes
        FROM planilla
        WHERE fecha = CURDATE() AND estado IN ('en_espera', 'en_atencion')
    `;

    db.query(sql, (err, results) => {
        if (err) {
            console.error('❌ Error al calcular tiempos restantes:', err.message);
            return res.status(500).json({ success: false, error: 'Error interno al consultar tiempos' });
        }

        const tiemposPorGrupo = {};
        results.forEach(({ operarios, minutos_restantes }) => {
            if (!tiemposPorGrupo[operarios]) {
                tiemposPorGrupo[operarios] = 0;
            }
            tiemposPorGrupo[operarios] += minutos_restantes;
        });

        const salida = Object.entries(tiemposPorGrupo).map(([grupo, total]) => ({
            operarios: grupo,
            minutos_restantes: total
        }));

        res.json({
            success: true,
            data: salida
        });
    });
});


const ExcelJS = require('exceljs');

app.get('/descargar-planilla', async (req, res) => {
    try {
        const fecha = req.query.fecha || moment().tz('America/Bogota').format('YYYY-MM-DD');
        const sql = 'SELECT placa, tipo_carro, servicios, precio_total, operarios, fecha, estado, rendimiento FROM planilla WHERE fecha = ?';

        db.query(sql, [fecha], async (err, rows) => {
            if (err) {
                console.error('Error al generar Excel:', err);
                return res.status(500).send('Error interno');
            }

            const workbook = new ExcelJS.Workbook();
            const worksheet = workbook.addWorksheet('Planilla');

            worksheet.columns = [
                { header: 'Placa', key: 'placa', width: 15 },
                { header: 'Tipo de carro', key: 'tipo_carro', width: 20 },
                { header: 'Servicios', key: 'servicios', width: 25 },
                { header: 'Precio Total', key: 'precio_total', width: 15 },
                { header: 'Operarios', key: 'operarios', width: 20 },
                { header: 'Fecha', key: 'fecha', width: 15 },
                { header: 'Estado', key: 'estado', width: 15 },
                { header: 'Rendimiento', key: 'rendimiento', width: 15 }
            ];

            worksheet.addRows(rows);

            res.setHeader('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
            res.setHeader('Content-Disposition', `attachment; filename=planilla_${fecha}.xlsx`);

            await workbook.xlsx.write(res);
            res.end();
        });
    } catch (err) {
        console.error('Error general al descargar planilla:', err);
        res.status(500).send('Error al generar archivo Excel');
    }
});

  

const PORT = process.env.PORT || 80;
server.listen(PORT, () => {
    console.log(`✅ Servidor corriendoo en http://localhost:${PORT}`);
    consultarTrabajosDeHoyPorGrupo();
});



