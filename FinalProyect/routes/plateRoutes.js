const express = require('express');
const db = require('../config/db');
const router = express.Router();

router.get('/plates', (req, res) => {
    console.log('Solicitando lista de placas...');
    const query = 'SELECT id, placa, timestamp FROM placas ORDER BY timestamp DESC';
    db.query(query, (err, results) => {
        if (err) {
            console.error('Error al obtener las placas de la base de datos:', err.message);
            res.status(500).send('Error interno del servidor.');
        } else {
            console.log('Placas obtenidas con éxito');
            res.json(results);
        }
    });
});

module.exports = router;
