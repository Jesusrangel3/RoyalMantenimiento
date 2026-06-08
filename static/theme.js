// ============================================
//  Taller CIF — Lógica del Toggle de Tema
//  ARCHIVO NUEVO: static/theme.js
// ============================================
(function () {
    'use strict';

    const html = document.documentElement;

    // --- Sincronizar ícono con el tema actual ---
    function syncIcon() {
        const btn = document.getElementById('theme-toggle-btn');
        if (!btn) return;
        const isDark = html.classList.contains('dark');
        btn.innerHTML = isDark
            ? '<i class="bi bi-sun-fill"></i>'
            : '<i class="bi bi-moon-fill"></i>';
        btn.title = isDark ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro';
    }

    // --- Función global para alternar el tema ---
    window.toggleTheme = function () {
        const isDark = html.classList.toggle('dark');
        try {
            localStorage.setItem('cif-theme', isDark ? 'dark' : 'light');
        } catch (e) { /* storage no disponible */ }
        syncIcon();
    };

    // --- Inicializar ícono al cargar la página ---
    syncIcon();
})();
