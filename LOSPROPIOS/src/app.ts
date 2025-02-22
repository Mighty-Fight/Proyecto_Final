import express from "express";
import path from "path";
import { fileURLToPath } from "url";
import { createBot, createFlow, MemoryDB, createProvider, addKeyword } from "@bot-whatsapp/bot";
import { BaileysProvider, handleCtx } from "@bot-whatsapp/provider-baileys";
import mysql from "mysql2/promise";

// Alternativa para __dirname en ESM
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Configuración del servidor Express
const app = express();
const PORT = 3000; // Puerto para servir la imagen en el navegador

// Ruta para servir la imagen
app.get("/", (req, res) => {
  const imagePath = path.join(__dirname, "../bot.qr.png"); // Ruta hacia la imagen
  res.sendFile(imagePath);
});

// Inicia el servidor Express
app.listen(PORT, "0.0.0.0", () => {
  console.log(`Servidor corriendo en http://34.234.95.122:${PORT}`);
});

// Variables para almacenar los precios de los servicios
let precioLavadoBasico: string | null = null;
let precioLavadoYEncerado: string | null = null;
let precioLavadoCompleto: string | null = null;

// Función para cargar los precios desde la base de datos
const cargarPreciosServicios = async () => {
  const connection = await mysql.createConnection({
    host: 'proyectofinaldb.cdiikyiuqv0u.us-east-1.rds.amazonaws.com',
    port: 3306,
    user: 'Milo',
    password: 'estrella10juju',
    database: 'ProyectoFinalDB',
  });

  try {
    const [lavadoBasico] = await connection.execute("SELECT precio FROM servicios WHERE nombre_servicio = ?", ["Lavado básico"]);
    const [lavadoYEncerado] = await connection.execute("SELECT precio FROM servicios WHERE nombre_servicio = ?", ["Lavado y encerado"]);
    const [lavadoCompleto] = await connection.execute("SELECT precio FROM servicios WHERE nombre_servicio = ?", ["Lavado completo"]);

    // Almacenar los precios en las variables globales
    precioLavadoBasico = (lavadoBasico as any[])[0]?.precio || "N/A";
    precioLavadoYEncerado = (lavadoYEncerado as any[])[0]?.precio || "N/A";
    precioLavadoCompleto = (lavadoCompleto as any[])[0]?.precio || "N/A";

    console.log("Precios cargados correctamente:", {
      precioLavadoBasico,
      precioLavadoYEncerado,
      precioLavadoCompleto,
    });
  } catch (error) {
    console.error("Error al cargar los precios desde la base de datos:", error);
  } finally {
    await connection.end();
  }
};

// Llamamos a cargarPreciosServicios una vez antes de iniciar el bot para tener los precios disponibles
await cargarPreciosServicios();

// Configuración del bot
const menuPrincipal = addKeyword("Hola").addAnswer(
  "¡Bienvenido a Lubriwash! ¿Qué desea hacer?\n\n1. Registrarme\n2. Consulta de precios\n3. Nada, parcharme\n\nPor favor, responde con el número de la opción deseada."
);

const opcionRegistrarme = addKeyword("1").addAnswer(
  "Para registrarte, por favor visita nuestro establecimiento o contáctanos directamente para obtener más información."
);

const mensajeConsultaPrecios = `Consulta de precios:\n\n1. Lavado básico: ${precioLavadoBasico}\n2. Lavado y encerado: ${precioLavadoYEncerado}\n3. Lavado completo: ${precioLavadoCompleto}`;
const opcionConsultaPrecios = addKeyword("2").addAnswer(mensajeConsultaPrecios);

const opcionNadaParcharme = addKeyword("3").addAnswer(
  "Perfecto, ¡puedes parcharte aquí todo lo que quieras! Si necesitas algo más, solo avísanos."
);

const flowNoEntiendo = addKeyword("").addAnswer(
  "No entiendo qué dices, ¿podrías repetir? Escribe 'Hola' para ver las opciones principales."
);

const main = async () => {
  const provider = createProvider(BaileysProvider);

  provider.initHttpServer(3002);

  provider.http?.server.post(
    "/buscar-placa",
    handleCtx(async (bot, req, res) => {
      const { placa } = req.body;

      const connection = await mysql.createConnection({
        host: 'proyectofinaldb.cdiikyiuqv0u.us-east-1.rds.amazonaws.com',
        port: 3306,
        user: 'Milo',
        password: 'estrella10juju',
        database: 'ProyectoFinalDB',
      });

      try {
        const [rows] = await connection.execute("SELECT nombre, telefono FROM usuarios WHERE placa = ?", [placa]);

        if ((rows as any[]).length > 0) {
          const usuario = rows[0];
          const mensaje = `Hola ${usuario.nombre}, acabas de llegar a Lubriwash. ¿Qué clase de servicio deseas el día de hoy?\n1. Consulta de precios\n2. Servicios adicionales\n\nEscribe el número de la opción deseada.`;

          await bot.sendMessage(usuario.telefono, mensaje, {});

          res.end(JSON.stringify({ mensaje: `Mensaje enviado a ${usuario.nombre} (${usuario.telefono}): "${mensaje}"` }));
        } else {
          res.end(JSON.stringify({ mensaje: `No se encontró ningún usuario con la placa ${placa}.` }));
        }
      } catch (error) {
        console.error("Error al consultar la base de datos:", error);
        res.end(JSON.stringify({ mensaje: "Error al consultar la base de datos." }));
      } finally {
        await connection.end();
      }
    })
  );

  await createBot({
    flow: createFlow([
      menuPrincipal,
      opcionRegistrarme,
      opcionConsultaPrecios,
      opcionNadaParcharme,
      flowNoEntiendo,
    ]),
    database: new MemoryDB(),
    provider,
  });

  console.log("Bot en funcionamiento...");
};

main();
