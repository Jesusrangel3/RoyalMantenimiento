// ============================================
//   Taller CIF — Dashboard Principal (script.js)
// ============================================

document.addEventListener('DOMContentLoaded', () => {

    // --- Socket.IO para actualizaciones en tiempo real ---
    const socket = io();
    socket.on('update', () => cargarEntradas());

    // --- Referencias DOM ---
    const dashContainer  = document.getElementById('dashboard-container');
    const loadingIndicator = document.getElementById('loading-indicator');
    const searchBar      = document.getElementById('search-bar');
    const formRegistro   = document.getElementById('form-registro');

    // --- Estado ---
    let filtroActual = 'todas';
    let searchTimer  = null;

    // ================================================
    //  INICIO: Cargar vehículos y entradas
    // ================================================
    cargarVehiculos();
    cargarEntradas();

    // ================================================
    //  VEHÍCULOS — TomSelect para el económico
    // ================================================
    let tomSelectEco = null;

    async function cargarVehiculos() {
        try {
            const res  = await fetch('/api/vehicles');
            const data = await res.json();

            if (document.getElementById('eco-select')) {
                tomSelectEco = new TomSelect('#eco-select', {
                    options: data.map(v => ({ value: v.name, text: v.name })),
                    create: true,
                    sortField: { field: 'text', direction: 'asc' },
                    placeholder: 'Buscar o escribir económico...',
                    maxOptions: 300,
                });
            }
        } catch (e) {
            console.warn('No se pudo cargar el catálogo de vehículos:', e);
            // Permitir TomSelect sin opciones predefinidas (modo libre)
            if (document.getElementById('eco-select')) {
                tomSelectEco = new TomSelect('#eco-select', { create: true, placeholder: 'Escribir económico...' });
            }
        }
    }

    // ================================================
    //  FILTROS
    // ================================================
    document.querySelectorAll('input[name="filtro-estado"]').forEach(radio => {
        radio.addEventListener('change', () => {
            filtroActual = radio.value;
            cargarEntradas();
        });
    });

    // ================================================
    //  BÚSQUEDA
    // ================================================
    if (searchBar) {
        searchBar.addEventListener('input', () => {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(() => cargarEntradas(), 350);
        });
    }

    // ================================================
    //  CARGA DE ENTRADAS
    // ================================================
    async function cargarEntradas() {
        if (loadingIndicator) loadingIndicator.style.display = 'block';

        const search = searchBar ? searchBar.value.trim() : '';
        const url    = `/api/entradas?filter=${filtroActual}&search=${encodeURIComponent(search)}`;

        try {
            const res  = await fetch(url);
            const data = await res.json();

            if (loadingIndicator) loadingIndicator.style.display = 'none';

            actualizarContadores(data.counts);
            renderizarTarjetas(data.entradas);

        } catch (e) {
            if (loadingIndicator) loadingIndicator.style.display = 'none';
            if (dashContainer) dashContainer.innerHTML = `
                <div class="col-12">
                    <div class="alert alert-danger">Error al cargar los datos: ${e.message}</div>
                </div>`;
        }
    }

    // ================================================
    //  ACTUALIZAR CONTADORES EN FILTROS
    // ================================================
    function actualizarContadores(counts) {
        if (!counts) return;
        const map = {
            'label-filtro-todas':        counts.todas,
            'label-filtro-en-tiempo':    counts.en_tiempo,
            'label-filtro-cerca-vencer': counts.cerca_de_vencer,
            'label-filtro-fuera-tiempo': counts.fuera_de_tiempo,
            'label-filtro-en-revision':  counts.en_revision,
        };
        Object.entries(map).forEach(([id, val]) => {
            const el = document.getElementById(id);
            if (!el) return;
            // Remover badge anterior
            el.querySelectorAll('.filtro-badge').forEach(b => b.remove());
            if (val > 0) {
                const badge = document.createElement('span');
                badge.className = 'filtro-badge bg-white text-dark';
                badge.textContent = val;
                el.appendChild(badge);
            }
        });
    }

    // ================================================
    //  RENDER TARJETAS
    // ================================================
    function renderizarTarjetas(entradas) {
        if (!dashContainer) return;

        if (!entradas || entradas.length === 0) {
            dashContainer.innerHTML = `
                <div class="col-12 empty-state">
                    <i class="bi bi-inbox"></i>
                    <h5 class="text-muted">No hay unidades en este filtro</h5>
                    <p class="text-muted small">Cambia el filtro o registra una nueva entrada.</p>
                </div>`;
            return;
        }

        dashContainer.innerHTML = entradas.map((e, i) => {
            const claseCard   = getClaseCard(e);
            const claseBadge  = getClaseBadge(e);
            const textoEstado = getTextoEstado(e);
            const razones     = Array.isArray(e.razones) ? e.razones.join(', ') : e.razones;

            // Barra de progreso días
            const pct = Math.min(100, Math.round((e.dias_en_taller / e.dias_estimados) * 100));
            const colorBar = e.excedido_por > 0 ? 'bg-danger' : (pct >= 75 ? 'bg-warning' : 'bg-success');

            const canEdit     = USER_PERMS.taller_editar || USER_ROLE === 'Superusuario';
            const canAutorizar= USER_PERMS.taller_autorizar || USER_ROLE === 'Superusuario';
            const canTecnico  = USER_PERMS.taller_tecnico || USER_ROLE === 'Superusuario';

            return `
            <div class="col-sm-6 col-xl-4 mb-3" id="card-wrapper-${e.id}" style="animation-delay:${i * 0.04}s">
                <div class="card card-unidad shadow-sm h-100 ${claseCard}">
                    <div class="card-body pb-2">
                        <!-- Cabecera -->
                        <div class="d-flex justify-content-between align-items-start mb-2">
                            <div>
                                <h5 class="fw-bold mb-0">${e.numero_economico}</h5>
                                <small class="text-muted">${e.tipo_vehiculo} &bull; ${e.area_name}</small>
                            </div>
                            <span class="badge ${claseBadge} rounded-pill px-3 py-2">${textoEstado}</span>
                        </div>

                        <!-- Motivo -->
                        <p class="mb-1 small"><i class="bi bi-wrench text-muted me-1"></i><strong>${razones || 'Sin motivo'}</strong></p>
                        ${e.otros_motivos ? `<p class="mb-1 small text-muted fst-italic">${e.otros_motivos}</p>` : ''}

                        <!-- Días -->
                        <div class="mt-2 mb-1">
                            <div class="d-flex justify-content-between align-items-center mb-1">
                                <small class="text-muted">Días en taller</small>
                                <small class="fw-bold ${e.excedido_por > 0 ? 'text-danger' : 'text-success'}">
                                    ${e.dias_en_taller} / ${e.dias_estimados} días
                                    ${e.excedido_por > 0 ? `<span class="badge bg-danger ms-1">+${e.excedido_por}</span>` : ''}
                                </small>
                            </div>
                            <div class="progress" style="height:6px;">
                                <div class="progress-bar ${colorBar}" style="width:${pct}%"></div>
                            </div>
                        </div>

                        <small class="text-muted d-block mt-2"><i class="bi bi-calendar3 me-1"></i>Entrada: ${e.fecha_entrada_str}</small>
                    </div>

                    <!-- Botones -->
                    <div class="card-footer bg-transparent border-0 pt-0 pb-3 px-3">
                        <div class="d-flex gap-1 flex-wrap">
                            <!-- Bitácora (todos con acceso pueden ver) -->
                            <button class="btn btn-outline-secondary btn-sm flex-grow-1"
                                onclick="abrirLog(${e.id}, '${e.numero_economico}')">
                                <i class="bi bi-journal-text me-1"></i>Bitácora
                            </button>

                            ${(canTecnico || canEdit) ? `
                            <button class="btn btn-outline-primary btn-sm flex-grow-1"
                                onclick="abrirAgregarNota(${e.id}, '${e.numero_economico}')">
                                <i class="bi bi-plus-circle me-1"></i>Nota
                            </button>` : ''}

                            ${canEdit ? `
                            <button class="btn btn-outline-warning btn-sm flex-grow-1"
                                onclick="abrirEditar(${e.id}, '${e.numero_economico}', '${razones}', ${e.dias_estimados}, \`${e.otros_motivos || ''}\`)">
                                <i class="bi bi-pencil me-1"></i>Editar
                            </button>` : ''}

                            ${canAutorizar ? `
                            ${e.status === 'pendiente' ? `
                            <button class="btn btn-outline-primary btn-sm flex-grow-1"
                                onclick="cambiarStatus(${e.id}, 'en_revision')">
                                <i class="bi bi-send me-1"></i>Autorizar
                            </button>` : `
                            <button class="btn btn-outline-success btn-sm flex-grow-1"
                                onclick="archivarEntrada(${e.id})">
                                <i class="bi bi-archive me-1"></i>Archivar
                            </button>`}` : ''}
                        </div>
                    </div>
                </div>
            </div>`;
        }).join('');
    }

    // ================================================
    //  HELPERS DE ESTADO
    // ================================================
    function getClaseCard(e) {
        if (e.status === 'en_revision')  return 'card-en-revision';
        if (e.excedido_por > 0)          return 'card-fuera-tiempo';
        const dias_restantes = e.dias_estimados - e.dias_en_taller;
        if (dias_restantes <= 2)         return 'card-cerca-vencer';
        return 'card-en-tiempo';
    }

    function getClaseBadge(e) {
        if (e.status === 'en_revision')  return 'badge-en-revision';
        if (e.excedido_por > 0)          return 'badge-fuera-tiempo';
        const dias_restantes = e.dias_estimados - e.dias_en_taller;
        if (dias_restantes <= 2)         return 'badge-cerca-vencer';
        return 'badge-en-tiempo';
    }

    function getTextoEstado(e) {
        if (e.status === 'en_revision')  return 'Por Autorizar';
        if (e.excedido_por > 0)          return `Excedido +${e.excedido_por}d`;
        const dias_restantes = e.dias_estimados - e.dias_en_taller;
        if (dias_restantes <= 2)         return `Vence en ${dias_restantes}d`;
        return 'En Tiempo';
    }

    // ================================================
    //  REGISTRO DE NUEVA ENTRADA
    // ================================================
    if (formRegistro) {
        formRegistro.addEventListener('submit', async (e) => {
            e.preventDefault();
            const eco = tomSelectEco ? tomSelectEco.getValue() : document.getElementById('eco-select').value;

            const body = {
                numero_economico: eco,
                tipo_vehiculo:    document.getElementById('tipo').value,
                razones:          document.getElementById('motivo-entrada-select').value,
                otros_motivos:    document.getElementById('otros-motivos').value.trim(),
                dias_estimados:   parseInt(document.getElementById('dias-estimados').value) || 1,
                fecha_entrada_manual: document.getElementById('fecha-entrada-manual').value || null,
            };

            if (!body.numero_economico || !body.razones) {
                alert('Por favor completa el económico y el motivo.');
                return;
            }

            const btn = formRegistro.querySelector('button[type="submit"]');
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Registrando...';

            try {
                const res = await fetch('/api/entradas', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body)
                });
                const data = await res.json();

                if (res.ok) {
                    formRegistro.reset();
                    if (tomSelectEco) tomSelectEco.clear();
                    document.getElementById('fecha-entrada-manual').value = '';
                    cargarEntradas();
                } else {
                    alert(data.error || 'Error al registrar.');
                }
            } catch (err) {
                alert('Error de conexión.');
            } finally {
                btn.disabled = false;
                btn.innerHTML = 'Registrar Entrada';
            }
        });
    }

    // ================================================
    //  EDITAR ENTRADA
    // ================================================
    window.abrirEditar = function(id, eco, razones, diasEst, otrosMotivos) {
        document.getElementById('edit-id').value      = id;
        document.getElementById('edit-eco').textContent = eco;
        document.getElementById('edit-estimado').value = diasEst;
        document.getElementById('edit-otros-motivos').value = otrosMotivos || '';

        // Seleccionar el motivo en el select
        const sel = document.getElementById('edit-motivo-select');
        for (let opt of sel.options) {
            if (opt.value === razones || razones.includes(opt.value)) {
                opt.selected = true;
                break;
            }
        }

        new bootstrap.Modal(document.getElementById('editModal')).show();
    };

    document.getElementById('btn-guardar-cambios')?.addEventListener('click', async () => {
        const id = document.getElementById('edit-id').value;
        const body = {
            razones:        document.getElementById('edit-motivo-select').value,
            otros_motivos:  document.getElementById('edit-otros-motivos').value.trim(),
            dias_estimados: parseInt(document.getElementById('edit-estimado').value),
        };

        const res = await fetch(`/api/entradas/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });

        if (res.ok) {
            bootstrap.Modal.getInstance(document.getElementById('editModal')).hide();
            cargarEntradas();
        } else {
            const err = await res.json();
            alert(err.error || 'Error al guardar.');
        }
    });

    // ================================================
    //  AGREGAR NOTA
    // ================================================
    window.abrirAgregarNota = function(id, eco) {
        document.getElementById('note-id').value = id;
        document.getElementById('note-eco').textContent = eco;
        document.getElementById('note-texto').value = '';
        new bootstrap.Modal(document.getElementById('addNoteModal')).show();
    };

    document.getElementById('btn-guardar-nota')?.addEventListener('click', async () => {
        const id   = document.getElementById('note-id').value;
        const text = document.getElementById('note-texto').value.trim();
        if (!text) return;

        const res = await fetch(`/api/entradas/${id}/nota`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text })
        });

        if (res.ok) {
            bootstrap.Modal.getInstance(document.getElementById('addNoteModal')).hide();
            cargarEntradas();
        } else {
            alert('Error al guardar la nota.');
        }
    });

    // ================================================
    //  VER HISTORIAL / LOG
    // ================================================
    window.abrirLog = async function(id, eco) {
        document.getElementById('log-eco').textContent = eco;
        document.getElementById('log-content').innerHTML = '';
        document.getElementById('log-spinner').style.display = 'block';
        new bootstrap.Modal(document.getElementById('viewLogModal')).show();

        try {
            const res   = await fetch(`/api/entradas/${id}/notas`);
            const notas = await res.json();
            document.getElementById('log-spinner').style.display = 'none';

            if (!notas || notas.length === 0) {
                document.getElementById('log-content').innerHTML =
                    '<p class="text-muted text-center py-3">Sin notas registradas.</p>';
                return;
            }

            document.getElementById('log-content').innerHTML = notas.map(n => `
                <div class="nota-item">
                    <p class="mb-1">${n.text}</p>
                    <div class="nota-meta">
                        <i class="bi bi-person-circle me-1"></i>${n.author || 'Sistema'}
                        &bull; ${n.timestamp}
                    </div>
                </div>`).join('');
        } catch (e) {
            document.getElementById('log-spinner').style.display = 'none';
            document.getElementById('log-content').innerHTML =
                '<p class="text-danger text-center py-3">Error al cargar el historial.</p>';
        }
    };

    // ================================================
    //  CAMBIAR STATUS (pendiente → en_revision)
    // ================================================
    window.cambiarStatus = async function(id, nuevoStatus) {
        const res = await fetch(`/api/entradas/${id}/status`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: nuevoStatus })
        });
        if (res.ok) cargarEntradas();
        else { const e = await res.json(); alert(e.error || 'Error.'); }
    };

    // ================================================
    //  ARCHIVAR ENTRADA
    // ================================================
    window.archivarEntrada = async function(id) {
        if (!confirm('¿Archivar esta unidad? Se moverá al historial.')) return;
        const res = await fetch(`/api/entradas/${id}/autorizar`, { method: 'PUT' });
        if (res.ok) cargarEntradas();
        else { const e = await res.json(); alert(e.error || 'Error al archivar.'); }
    };

});
