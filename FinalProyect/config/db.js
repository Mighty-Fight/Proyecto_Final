const mysql = require('mysql2');
const path = require('path');
const dotenv = require('dotenv');

// 🔍 Detectar si está en AWS o en local
const envPath = process.env.NODE_ENV === 'production' 
    ? path.resolve(__dirname, '../FinalProyect/.env')  // Para EC2
    : path.resolve(__dirname, '../.env'); // Para local

dotenv.config({ path: envPath });

const db = mysql.createConnection({
    host: process.env.DB_HOST,
    user: process.env.DB_USER,
    password: process.env.DB_PASSWORD,
    database: process.env.DB_NAME
});

db.connect((err) => {
    if (err) {
        console.error('Error conectando a la base de datos:', err.message);
        return;
    }
    console.log('Conectado a la base de datos MySQL.');
});

module.exports = db;
