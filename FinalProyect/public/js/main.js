document.addEventListener("DOMContentLoaded", function() {
    console.log("JavaScript cargado correctamente");

    const logoutButton = document.getElementById("logout-button");
    if (logoutButton) {
        logoutButton.addEventListener("click", function() {
            console.log("Cerrando sesión...");
            fetch("/logout").then(() => {
                window.location.href = "/login";
            });
        });
    }

    // Manejo de errores en formularios
    const form = document.querySelector("form");
    if (form) {
        form.addEventListener("submit", function(event) {
            const inputs = form.querySelectorAll("input");
            let valid = true;
            inputs.forEach(input => {
                if (!input.value.trim()) {
                    valid = false;
                    input.classList.add("error");
                } else {
                    input.classList.remove("error");
                }
            });
            if (!valid) {
                event.preventDefault();
                alert("Todos los campos son obligatorios");
            }
        });
    }
});
