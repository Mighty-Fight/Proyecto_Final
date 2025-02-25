const db = require('../config/db');
const bcrypt = require('bcrypt');

class User {
    static async create(username, password, callback) {
        console.log(`Registrando usuario: ${username}`);
        const hashedPassword = await bcrypt.hash(password, 10);
        const query = 'INSERT INTO users (username, password) VALUES (?, ?)';
        db.query(query, [username, hashedPassword], callback);
    }

    static findByUsername(username, callback) {
        console.log(`Buscando usuario: ${username}`);
        const query = 'SELECT * FROM users WHERE username = ?';
        db.query(query, [username], callback);
    }
}

module.exports = User;
