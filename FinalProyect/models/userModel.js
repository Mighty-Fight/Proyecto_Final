const db = require("../config/db");

const createUserTable = () => {
    const query = `
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    `;
    db.query(query, (err) => {
        if (err) {
            console.error("Error creando la tabla de usuarios:", err.message);
        } else {
            console.log("Tabla 'users' verificada/correcta.");
        }
    });
};

createUserTable();

module.exports = {};
