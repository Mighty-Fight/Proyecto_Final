const { createBot, createProvider, createFlow, addKeyword } = require('@bot-whatsapp/bot')

const QRPortalWeb = require('@bot-whatsapp/portal')
const BaileysProvider = require('@bot-whatsapp/provider/baileys')
const MockAdapter = require('@bot-whatsapp/database/mock')

const flowCombos = addKeyword('5').addAnswer( 
    `🎁 *Precios - Combos:*
- Brillado máquina automóvil: $90.000
- Brillado máquina campero: $100.000
- Combo diamond automóvil: $276.000
- Combo diamond campero: $300.000
- Combo gold automóvil: $138.000
- Combo gold campero: $161.000
- Combo platino automóvil: $402.000
- Combo platino campero: $437.000
- Desmanche fuerte por pieza: $30.000
- Desmanche por pieza: $20.000
- Hidratación automóvil: $90.000
- Hidratación campero: $110.000
Escribe *Hola* para volver al menu principal`);



const flowTecnicentro = addKeyword('4').addAnswer(
    `⚙️ *Precios - Tecnicentro:*
- Alineación automóvil: $45.000
- Alineación campero: $50.000
- Alineación de luces: $20.000
- Alineación taxi: $35.000
- Alineación + balanceo + rotación automóvil: $70.000
- Alineación + balanceo taxi: $45.000
- Alineación + balanceo + lavado automóvil: $85.000
- Alineación + balanceo + lavado campero: $95.000
- Alineación + balanceo + rotación campero: $80.000
- Balanceado automóvil x llanta: $15.000
- Balanceado automóvil completo: $40.000
- Balanceado campero completo: $50.000
- Balanceado campero x llanta: $20.000
- Balanceado taxi completo: $35.000
- Balanceado taxi x llanta: $7.000
- Calibración de válvula: $80.000
- Desvare: $40.000
- Diagnóstico: $25.000
- Montaje blindado: $30.000
- Montaje llanta automóvil: $15.000
- Montaje llanta campero: $20.000
- Montaje taxi: $5.000
- Recarga de batería: $12.000
- Reparación de llanta automóvil: $22.000
- Reparación de llanta campero: $27.000
- Revisión de freno: $30.000
- Revisión sincronización: $25.000
- Rotación automóvil: $15.000
- Rotación campero: $20.000
- Servicio cambio de aceite: $40.000
Escribe *Hola* para volver al menu principal`);


const flowServicios = addKeyword('3').addAnswer(
    `🛠️ *Precios - Servicios Especializados:*
- Impermeabilización M.O.: $500.000
- Overhaul automóvil: $280.000
- Overhaul campero: $300.000
- Polichado automóvil: $150.000
- Polichado campero: $180.000
- Porcelanizada automóvil: $253.000
- Porcelanizada campero: $276.000
- Restauración de farolas: $40.000
- Restauración partes negras: $20.000
Escribe *Hola* para volver al menu principal`);


const flowMano = addKeyword('2').addAnswer(
    `🔧 *Precios - Mano de Obra:*
- Banco de prueba: $60.000
- Domicilio: $10.000
- Mano de obra arreglo cárter: $200.000
- Mec. amortiguadores delantero: $50.000
- Mec. amortiguadores trasero: $40.000
- Mec. brazo axiales: $30.000
- Mec. cambio correa tiempo: $190.000
- Mec. cambio empaque: $60.000
- Mec. cambio líquido freno: $130.000
- Mec. cambio refrigerante: $40.000
- Mec. cambio tijeras: $40.000
- Mec. filtro combustible: $30.000
- Mec. soporte amortiguador: $40.000
- Mec. soporte motor: $40.000
- Servicio escáner: $60.000
Escribe *Hola* para volver al menu principal`);


const flowLavados = addKeyword('1').addAnswer(
    `🚗💦 *Precios - Lavados:*
- Adicional barro: $15.000
- Combo 2 automóvil: $45.000
- Combo 2 campero: $55.000
- Combo 2 moto: $20.000
- Combo 3 automóvil: $56.000
- Combo 3 campero: $64.000
- Lavado automóvil: $30.000
- Lavado campero: $35.000
- Lavado moto: $15.000
Escribe *Hola* para volver al menu principal`);


const flowPrecios = addKeyword('1')
    .addAnswer([
        '📋 *Estos son los precios disponibles*. Por favor, escribe el número correspondiente a la categoría que deseas consultar:',
        '',
        '1️⃣ Lavados',
        '2️⃣ Mano de Obra',
        '3️⃣ Servicios Especializados',
        '4️⃣ Tecnicentro',
        '5️⃣ Combos',
    ], null, null, [flowLavados, flowMano, flowServicios, flowTecnicentro, flowCombos])

const flowRedes = addKeyword('2')
    .addAnswer(['🌐 Nuestras redes sociales son:',
        'https://www.instagram.com/lubriwash84/?hl=es',
        'Escribe *Hola* para volver al menu principal'
    ])

const flowQuejas = addKeyword('3')
    .addAnswer(['📢 Cuéntanos tu queja o reclamo...',
        'Escribe *Hola* para volver al menu principal'

    ])

const flowSushi = addKeyword('4')
    .addAnswer(['🍣 Este es nuestro menú de Sushi...',
        'https://watamicolombia.com/',
        'Escribe *Hola* para volver al menu principal'
    ])

// --- Flow Principal ---
const flowPrincipal = addKeyword(['hola'])
    .addAnswer('🙌 ¡Hola! Bienvenido a *LubryWash* 🚗✨')
    .addAnswer([
        'Selecciona una opción:',
        '1️⃣ Consulta de precios',
        '2️⃣ Redes sociales',
        '3️⃣ Quejas',
        '4️⃣ Menú Sushi'
    ], null, null, [flowPrecios, flowRedes, flowQuejas, flowSushi])

const main = async () => {
    const adapterDB = new MockAdapter()
    const adapterFlow = createFlow([flowPrincipal])
    const adapterProvider = createProvider(BaileysProvider)

    createBot({
        flow: adapterFlow,
        provider: adapterProvider,
        database: adapterDB,
    })

    QRPortalWeb()
}

main()
