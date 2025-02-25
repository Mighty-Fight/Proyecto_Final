const express = require('express');
const bcrypt = require('bcrypt');
const db = require('../config/db');
const router = express.Router();
const path = require('path');

router.get('/login', (req, res) => {
    console.log("Renderizando página de login");
    res.sendFile(path.join(__dirname, '../public', 'login.html'));
});

router.post('/login', (req, res) => {
    const { username, password } = req.body;
    console.log(`Intento de inicio de sesión para: ${username}`);

    const query = 'SELECT * FROM users WHERE username = ?';
    db.query(query, [username], async (err, results) => {
        if (err) {
            console.error('Error en login:', err.message);
            return res.status(500).send('Error interno.');
        }
        if (results.length === 0) {
            console.log('Usuario no encontrado');
            return res.send('Usuario no encontrado.');
        }

        const user = results[0];
        const match = await bcrypt.compare(password, user.password);
        if (match) {
            req.session.user = user;
            console.log(`Inicio de sesión exitoso: ${username}`);
            res.redirect('/');
        } else {
            console.log('Contraseña incorrecta');
            res.send('Contraseña incorrecta.');
        }
    });
});

module.exports = router;
