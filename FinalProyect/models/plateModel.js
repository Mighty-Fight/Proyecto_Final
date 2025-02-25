const db = require('../config/db');

class Plate {
    static getAll(callback) {
        console.log('Obteniendo todas las placas...');
        const query = 'SELECT id, placa, timestamp FROM placas ORDER BY timestamp DESC';
        db.query(query, callback);
    }

    static search({ placa, startTimestamp, endTimestamp }, callback) {
        console.log(`Buscando placas con filtros - Placa: ${placa}, Desde: ${startTimestamp}, Hasta: ${endTimestamp}`);
        let query = 'SELECT * FROM placas WHERE 1=1';
        const params = [];

        if (placa) {
            query += ' AND placa LIKE ?';
            params.push(`%${placa}%`);
        }
        if (startTimestamp) {
            query += ' AND timestamp >= ?';
            params.push(startTimestamp);
        }
        if (endTimestamp) {
            query += ' AND timestamp <= ?';
            params.push(endTimestamp);
        }

        db.query(query, params, callback);
    }
}

module.exports = Plate;
