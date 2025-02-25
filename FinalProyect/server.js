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
    saveUninitialized: true,
}));

app.use(express.static(path.join(__dirname, 'public')));
app.use(express.urlencoded({ extended: true }));
app.use(bodyParser.json());

// Rutas de autenticación y placas
app.use('/', authRoutes);
app.use('/plates', plateRoutes);

// Ruta protegida
app.get('/', isAuthenticated, (req, res) => {
    console.log(`Usuario autenticado: ${req.session.user.username}`);
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// Ruta para obtener información del usuario autenticado
app.get('/user-info', isAuthenticated, (req, res) => {
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
app.post('/update', (req, res) => {
    const { placa } = req.body;
    const timestamp = new Date();
    if (placa) {
        console.log(`Nueva placa recibida: ${placa}`);
        placaStatus = placa;
        io.emit('updatePlaca', { placa, timestamp: timestamp.toLocaleString() });

        db.query('INSERT INTO placas (placa, timestamp) VALUES (?, ?)', [placa, timestamp], (err) => {
            if (err) {
                console.error('Error al insertar en la base de datos:', err.message);
                res.status(500).send('Error interno.');
            } else {
                console.log(`Placa "${placa}" guardada en la base de datos.`);
                res.sendStatus(200);
            }
        });
    } else {
        console.warn('Placa no proporcionada en la solicitud.');
        res.status(400).send('Placa no proporcionada.');
    }
});

const PORT = process.env.PORT || 3000;
server.listen(PORT, () => {
    console.log(`Servidor corriendo en http://localhost:${PORT}`);
});
