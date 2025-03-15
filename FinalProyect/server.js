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

const app = express();
const server = http.createServer(app);
const io = socketIo(server);

require('dotenv').config();

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

io.on('connection', (socket) => {
    console.log('Usuario conectado');
    socket.emit('updatePlaca', { placa: placaStatus, timestamp: new Date().toLocaleString() });
    
    socket.on('disconnect', () => {
        console.log('Usuario desconectado');
    });
});

// Recibir placas desde `camnew.py`
let lastPlate = ''; // Variable para almacenar la última placa registrada

app.post('/update', (req, res) => {
    const { placa, frame } = req.body;
    const timestamp = new Date();

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
    io.emit('updatePlaca', { placa, timestamp: timestamp.toLocaleString(), frame });
    
    db.query('INSERT INTO placas (placa, timestamp) VALUES (?, ?)', [placa, timestamp], (err) => {
        if (err) {
            console.error('Error al insertar en la base de datos:', err.message);
            return res.status(500).json({ success: false, error: 'Error interno.' });
        } else {
            console.log(`Placa "${placa}" guardada en la base de datos.`);
            return res.json({ success: true, placa });
        }
    });
});

app.get('/get-plates', (req, res) => {
    let { plate, startDate, endDate } = req.query;
    let sql = 'SELECT id, placa, timestamp FROM placas';
    let params = [];

    if (plate || startDate || endDate) {
        // Si se aplican filtros, construye las condiciones
        let conditions = [];
        if (plate) {
            conditions.push('placa LIKE ?');
            params.push(`%${plate}%`);
        }
        if (startDate) {
            conditions.push('timestamp >= ?');
            params.push(startDate);  // Asegúrate de que el formato sea compatible
        }
        if (endDate) {
            conditions.push('timestamp <= ?');
            params.push(endDate);
        }
        if (conditions.length > 0) {
            sql += ' WHERE ' + conditions.join(' AND ');
        }
    } else {
        // Si no se especifican filtros, se devuelven los registros del día actual
        // Ejemplo: 2025-03-14 00:00:00 hasta 2025-03-14 23:59:59
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



// Iniciar el servidor en el puerto configurado
const PORT = process.env.PORT || 80;
server.listen(PORT, () => {
    console.log(`✅ Servidor corriendo en http://localhost:${PORT}`);
});
