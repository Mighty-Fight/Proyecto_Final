function isAuthenticated(req, res, next) {
    if (req.session.user) {
        console.log(`Usuario autenticado: ${req.session.user.username}`);
        return next();
    }
    console.log('Acceso denegado: Usuario no autenticado');
    res.redirect('/login');
}

module.exports = { isAuthenticated };
