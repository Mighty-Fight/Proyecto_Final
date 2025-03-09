const express = require("express");
const bcrypt = require("bcryptjs");
const db = require("../config/db");
const router = express.Router();

// 📌 Registro de usuario
router.post("/register", async (req, res) => {
    const { username, email, password } = req.body;

    if (!username || !email || !password) {
        return res.status(400).json({ message: "Todos los campos son obligatorios." });
    }

    try {
        const hashedPassword = await bcrypt.hash(password, 10);
        const query = "INSERT INTO users (username, email, password) VALUES (?, ?, ?)";

        db.query(query, [username, email, hashedPassword], (err) => {
            if (err) {
                console.error("Error en el registro:", err.message);
                return res.status(500).json({ message: "Error al registrar el usuario." });
            }
            res.json({ message: "Registro exitoso. Redirigiendo al login..." });
        });
    } catch (error) {
        console.error("Error en el registro:", error);
        res.status(500).json({ message: "Error interno del servidor." });
    }
});

// 📌 Login de usuario
// 📌 Login de usuario
router.post("/login", (req, res) => {
    const { username, password } = req.body;

    if (!username || !password) {
        return res.status(400).json({ message: "Todos los campos son obligatorios." });
    }

    const query = "SELECT * FROM users WHERE username = ?";
    db.query(query, [username], async (err, results) => {
        if (err) {
            console.error("Error en login:", err.message);
            return res.status(500).json({ message: "Error interno del servidor." });
        }

        if (results.length === 0) {
            return res.status(401).json({ message: "Usuario no encontrado." });
        }

        const user = results[0];
        const match = await bcrypt.compare(password, user.password);
        if (!match) {
            return res.status(401).json({ message: "Contraseña incorrecta." });
        }

        // ✅ Asegurar que la sesión se guarda antes de responder
        req.session.regenerate((err) => {
            if (err) {
                console.error("Error regenerando la sesión:", err);
                return res.status(500).json({ message: "Error interno de sesión." });
            }

            req.session.user = { id: user.id, username: user.username };
            console.log("✅ Usuario autenticado, redirigiendo...");

            // ✅ Confirmar que la sesión se guarda antes de responder
            req.session.save((err) => {
                if (err) {
                    console.error("Error guardando la sesión:", err);
                    return res.status(500).json({ message: "Error interno del servidor." });
                }

                res.json({ message: "Login exitoso. Redirigiendo...", redirect: "/dashboard" });

            });
        });
    });
});


// 📌 Cerrar sesión
router.get("/logout", (req, res) => {
    req.session.destroy(() => {
        res.redirect("/login.html");
    });
});

module.exports = router;
