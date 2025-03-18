document.addEventListener("DOMContentLoaded", () => {
    const menu = document.getElementById("menu");
    const hamburger = document.querySelector(".menu-icon");
    const registerForm = document.getElementById("register-form");
    const loginForm = document.getElementById("login-form");
    const feedbackForm = document.getElementById("feedback-form");

    // 🔹 Verificar si los elementos existen
    console.log("Menu encontrado:", menu);
    console.log("Hamburguesa encontrada:", hamburger);

    // ✅ Alternar menú hamburguesa
    function toggleMenu() {
        if (menu) {
            menu.classList.toggle("active");
        }
    }

    // ✅ Asegurar que el botón hamburguesa funcione
    if (hamburger && menu) {
        hamburger.addEventListener("click", toggleMenu);
        
        // ✅ Cerrar menú al hacer clic en una opción
        menu.addEventListener("click", (event) => {
            if (event.target.tagName === "A") {
                menu.classList.remove("active");
            }
        });
    }

    // ✅ Registro de usuario
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

            // ✅ Validaciones básicas
            if (!username || !email || !password || !confirmPassword) {
                messageElement.innerText = "Todos los campos son obligatorios.";
                return;
            }

            if (password !== confirmPassword) {
                messageElement.innerText = "Las contraseñas no coinciden.";
                return;
            }

            // ✅ Evitar múltiples envíos
            registerForm.querySelector("button").disabled = true;

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
                } else {
                    registerForm.querySelector("button").disabled = false;
                }
            } catch (error) {
                console.error("Error en el registro:", error);
                messageElement.innerText = "Error en el servidor. Inténtalo de nuevo.";
                registerForm.querySelector("button").disabled = false;
            }
        });
    }

    // ✅ Inicio de sesión
    if (loginForm) {
        loginForm.addEventListener("submit", async (event) => {
            event.preventDefault();

            const formData = new FormData(loginForm);
            const username = formData.get("username").trim();
            const password = formData.get("password");

            const messageElement = document.getElementById("login-message");
            if (!messageElement) return;

            // ✅ Validaciones básicas
            if (!username || !password) {
                messageElement.innerText = "Usuario y contraseña son obligatorios.";
                return;
            }

            // ✅ Evitar múltiples envíos
            loginForm.querySelector("button").disabled = true;

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
                    loginForm.querySelector("button").disabled = false;
                }
            } catch (error) {
                console.error("Error en el login:", error);
                messageElement.innerText = "Error en el servidor. Inténtalo de nuevo.";
                loginForm.querySelector("button").disabled = false;
            }
        });
    }

    // ✅ Envío del feedback del cliente
    if (feedbackForm) {
        feedbackForm.addEventListener("submit", async (event) => {
            event.preventDefault(); // Evita el envío estándar del formulario

            const comentario = document.getElementById("feedback-comment").value.trim();
            const feedbackMessage = document.getElementById("feedback-message");

            if (!comentario) {
                feedbackMessage.innerText = "Por favor, escribe tu opinión.";
                feedbackMessage.style.color = "red";
                return;
            }

            try {
                const response = await fetch("/submit-feedback", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ comentario })
                });

                const data = await response.json();
                feedbackMessage.innerText = data.message;
                feedbackMessage.style.color = data.success ? "green" : "red";

                if (data.success) {
                    feedbackForm.reset(); // Limpiar el formulario tras el envío exitoso
                }
            } catch (error) {
                console.error("Error enviando feedback:", error);
                feedbackMessage.innerText = "Hubo un error. Inténtalo de nuevo.";
                feedbackMessage.style.color = "red";
            }
        });
    }
});





