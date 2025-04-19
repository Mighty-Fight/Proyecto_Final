const { createBot, createProvider, createFlow, addKeyword } = require('@bot-whatsapp/bot');
const BaileysProvider = require('@bot-whatsapp/provider/baileys');
const MockAdapter = require('@bot-whatsapp/database/mock');

const main = async () => {
    const provider = createProvider(BaileysProvider);
    const flow = createFlow([addKeyword('ping').addAnswer('pong')]);
    const db = new MockAdapter();

    await createBot({
        flow,
        provider,
        database: db,
    });

    console.log("⏳ Esperando 10 segundos antes de enviar mensaje...");

    // Espera para dar tiempo a que se escanee el QR
    setTimeout(async () => {
        try {
            const numero = '+573117561446'; // 🔁 Reemplaza por tu número real
            const chatId = numero.includes('@c.us') ? numero : `${numero}@c.us`;
            const mensaje = '✅ Mensaje enviado directamente sin getInstance()';

            await provider.sendText(chatId, mensaje);
            console.log(`✅ Mensaje enviado a ${chatId}`);
        } catch (err) {
            console.error("❌ Error al enviar el mensaje:", err.message);
        }
    }, 10000); // 10 segundos
};

main();
