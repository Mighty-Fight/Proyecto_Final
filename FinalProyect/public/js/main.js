document.addEventListener("DOMContentLoaded", () => {
    const registerForm = document.getElementById("register-form");
    const loginForm = document.getElementById("login-form");

    // Registro de usuario
    if (registerForm) {
        registerForm.addEventListener("submit", async (event) => {
            event.preventDefault();
            const formData = new FormData(registerForm);
            const username = formData.get("username").trim();
            const email = formData.get("email").trim();
            const password = formData.get("password");
            const confirmPassword = formData.get("confirmPassword");

            const messageElement = document.getElementById("register-message");
            if (!messageElement) return;

            if (!username || !email || !password || !confirmPassword) {
                messageElement.innerText = "Todos los campos son obligatorios.";
                return;
            }

            if (password !== confirmPassword) {
                messageElement.innerText = "Las contraseñas no coinciden.";
                return;
            }

            try {
                const response = await fetch("/register", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ username, email, password })
                });

                const data = await response.json();
                messageElement.innerText = data.message;

                if (response.ok) {
                    setTimeout(() => {
                        window.location.href = "/login.html";
                    }, 2000);
                }
            } catch (error) {
                console.error("Error en el registro:", error);
                messageElement.innerText = "Error en el servidor. Inténtalo de nuevo.";
            }
        });
    }

    // Inicio de sesión
    if (loginForm) {
        loginForm.addEventListener("submit", async (event) => {
            event.preventDefault();
            const formData = new FormData(loginForm);
            const username = formData.get("username").trim();
            const password = formData.get("password");

            const messageElement = document.getElementById("login-message");
            if (!messageElement) return;

            if (!username || !password) {
                messageElement.innerText = "Usuario y contraseña son obligatorios.";
                return;
            }

            try {
                const response = await fetch("/login", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ username, password })
                });

                const data = await response.json();
                messageElement.innerText = data.message;

                if (response.ok) {
                    console.log("Redirigiendo a:", data.redirect);
                    setTimeout(() => {
                        window.location.replace(data.redirect);
                    }, 2000);
                } else {
                    console.error("Error en login:", data.message);
                }
                
            } catch (error) {
                console.error("Error en el login:", error);
                messageElement.innerText = "Error en el servidor. Inténtalo de nuevo.";
            }
        });
    }
});
