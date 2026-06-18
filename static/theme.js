// ============================================
//  Taller CIF — Lógica del Toggle de Tema y Sidebar Colapsable
//  ============================================
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

    // --- Lógica del Sidebar Colapsable ---
    function initSidebar() {
        const toggleBtn = document.getElementById('sidebar-toggle-btn');
        if (!toggleBtn) return;

        // Cargar estado inicial de localStorage
        const sidebarState = localStorage.getItem('cif-sidebar-state') || 'expanded';
        if (sidebarState === 'collapsed') {
            html.classList.add('sidebar-collapsed');
            syncSidebarIcon(true);
        } else {
            html.classList.remove('sidebar-collapsed');
            syncSidebarIcon(false);
        }

        toggleBtn.addEventListener('click', function(e) {
            e.preventDefault();
            const isCollapsed = html.classList.toggle('sidebar-collapsed');
            try {
                localStorage.setItem('cif-sidebar-state', isCollapsed ? 'collapsed' : 'expanded');
            } catch (err) { /* storage no disponible */ }
            syncSidebarIcon(isCollapsed);
        });
    }

    // --- Sincronizar icono del botón colapso ---
    function syncSidebarIcon(isCollapsed) {
        const toggleBtn = document.getElementById('sidebar-toggle-btn');
        if (!toggleBtn) return;
        const icon = toggleBtn.querySelector('i');
        if (icon) {
            if (isCollapsed) {
                icon.className = 'bi bi-layout-sidebar';
            } else {
                icon.className = 'bi bi-layout-sidebar-inset';
            }
        }
    }

    // --- Inicializar al cargar el DOM ---
    document.addEventListener('DOMContentLoaded', () => {
        syncIcon();
        initSidebar();
    });
})();
