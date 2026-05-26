document.addEventListener('DOMContentLoaded', () => {

    // --- Referencias a Elementos ---
    const statsContainer = document.getElementById('stats-container');
    const loadingIndicator = document.getElementById('stats-loading');
    
    // Obtener estado de la URL (activas o archivadas)
    const pathParts = window.location.pathname.split('/');
    const status = pathParts[pathParts.length - 1]; 
    
    // Variables para los gráficos
    let chartMotivos = null;
    let chartOperaciones = null;
    let chartTipos = null; // NUEVO: Gráfico de Tipos de Vehículo
    let rawOpsData = []; 
    let summaryData = []; 
    let rawTiposData = []; // NUEVO: Datos para tipos de vehículo
    
    // --- Carga Inicial ---
    cargarTodo(status);
    
    // Función para limpiar etiquetas (por si el backend tiene pendientes)
    function limpiarEtiqueta(nombre) {
        if (!nombre) return "Sin Clasificar";
        return nombre.replace(/\s+rastreos\s+principales/gi, '').trim();
    }

    async function cargarTodo(status) {
        if (loadingIndicator) loadingIndicator.style.display = 'block';
        if (statsContainer) statsContainer.innerHTML = '';
        
        try {
            // Peticiones en paralelo a los 3 endpoints
            const [resSummary, resOps, resTipos] = await Promise.all([
                fetch(`/api/statistics/summary/${status}`),
                fetch(`/api/statistics/operations/${status}`),
                fetch(`/api/statistics/vehicletypes/${status}`) // NUEVO ENDPOINT
            ]);

            if (!resSummary.ok || !resOps.ok || !resTipos.ok) throw new Error('Error en la respuesta del servidor');

            summaryData = await resSummary.json();
            const rawOps = await resOps.json();
            rawTiposData = await resTipos.json(); // Cargar los tipos de vehículo

            // Limpiamos y agrupamos en frontend para evitar duplicados por minúsculas o espacios
            const groupedMap = new Map();
            rawOps.forEach(item => {
                const label = limpiarEtiqueta(item.operacion);
                if (groupedMap.has(label)) {
                    const existing = groupedMap.get(label);
                    existing.total += item.total;
                    existing.unidades = [...new Set([...existing.unidades, ...item.unidades])];
                } else {
                    groupedMap.set(label, {
                        operacion: label,
                        total: item.total,
                        unidades: item.unidades
                    });
                }
            });
            rawOpsData = Array.from(groupedMap.values());

            if (loadingIndicator) loadingIndicator.style.display = 'none';
            
            if (statsContainer) {
                statsContainer.innerHTML = `
                    <div class="row mb-4">
                        <!-- Gráfico 1: Motivos (Ancho completo arriba) -->
                        <div class="col-12 mb-4">
                            <div class="card shadow-sm h-100 border-0">
                                <div class="card-body">
                                    <h5 class="card-title text-center text-primary fw-bold">Unidades por Motivo de Entrada</h5>
                                    <div style="position: relative; height:320px;">
                                        <canvas id="chart-motivos"></canvas>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Gráfico 2: Operaciones (Samsara) -->
                        <div class="col-lg-6 mb-4">
                            <div class="card shadow-sm h-100 border-0">
                                <div class="card-body">
                                    <h5 class="card-title text-center text-success fw-bold">Unidades por Operación (Samsara)</h5>
                                    <p class="small text-muted text-center mb-0"><i class="bi bi-info-circle-fill"></i> Haz clic en un área para ver detalles</p>
                                    <div style="position: relative; height:300px; display:flex; justify-content:center;">
                                        <canvas id="chart-operaciones"></canvas>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- NUEVO Gráfico 3: Tipo de Vehículo -->
                        <div class="col-lg-6 mb-4">
                            <div class="card shadow-sm h-100 border-0">
                                <div class="card-body">
                                    <h5 class="card-title text-center text-info fw-bold">Unidades por Tipo de Vehículo</h5>
                                    <p class="small text-muted text-center mb-0"><i class="bi bi-info-circle-fill"></i> Haz clic en el tipo para ver detalles</p>
                                    <div style="position: relative; height:300px; display:flex; justify-content:center;">
                                        <canvas id="chart-tipos"></canvas>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- SECCIÓN DINÁMICA: Detalle por Selección (Compartido para Áreas y Tipos) -->
                    <div id="detalle-operacion-container" class="mb-4" style="display:none;">
                        <div class="card border-0 shadow-lg">
                            <div class="card-header bg-dark text-white d-flex justify-content-between align-items-center py-3">
                                <h6 class="mb-0 fs-5"><i class="bi bi-funnel-fill me-2"></i> Unidades en: <span id="op-selected-name" class="text-warning"></span></h6>
                                <button type="button" class="btn-close btn-close-white" onclick="document.getElementById('detalle-operacion-container').style.display='none'"></button>
                            </div>
                            <div class="card-body bg-light">
                                <div id="op-selected-units" class="d-flex flex-wrap gap-2 justify-content-center"></div>
                            </div>
                        </div>
                    </div>

                    <!-- Tabla General -->
                    <div class="row">
                        <div class="col-12">
                            <div class="card shadow-sm border-0">
                                <div class="card-header bg-secondary text-white py-3">
                                    <h5 class="mb-0"><i class="bi bi-table me-2"></i> Resumen Detallado de Tiempos</h5>
                                </div>
                                <div class="card-body p-0">
                                    <div class="table-responsive" id="tabla-container"></div>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
                
                renderizarTabla(summaryData);
                renderizarGraficoMotivos(summaryData);
                renderizarGraficoOperaciones(rawOpsData);
                renderizarGraficoTipos(rawTiposData); // Llama al renderizado del nuevo gráfico
            }

        } catch (error) {
            console.error(error);
            if (loadingIndicator) loadingIndicator.style.display = 'none';
            if (statsContainer) statsContainer.innerHTML = `<div class="alert alert-danger shadow-sm">Error: ${error.message}</div>`;
        }
    }
    
    function renderizarTabla(data) {
        const container = document.getElementById('tabla-container');
        if (!container) return;
        
        let tableHtml = `
            <table class="table table-hover align-middle mb-0">
                <thead class="table-light">
                    <tr>
                        <th class="ps-4">Motivo de Entrada</th>
                        <th class="text-center">1-3 Días</th>
                        <th class="text-center">4-8 Días</th>
                        <th class="text-center">9+ Días</th>
                        <th class="text-center fw-bold pe-4">Total</th>
                    </tr>
                </thead>
                <tbody>
        `;
        
        let t1=0, t2=0, t3=0, total=0;
        if (data.length === 0) {
            tableHtml += `<tr><td colspan="5" class="text-center text-muted p-5">No hay datos activos para este periodo.</td></tr>`;
        } else {
            data.forEach(row => {
                tableHtml += `<tr>
                    <td class="ps-4"><strong>${row.motivo}</strong></td>
                    <td class="text-center"><span class="badge rounded-pill bg-success-subtle text-success px-3">${row['1-3 Días']}</span></td>
                    <td class="text-center"><span class="badge rounded-pill bg-warning-subtle text-warning px-3">${row['4-8 Días']}</span></td>
                    <td class="text-center"><span class="badge rounded-pill bg-danger-subtle text-danger px-3">${row['9+ Días']}</span></td>
                    <td class="text-center fw-bold pe-4">${row.total}</td>
                </tr>`;
                t1 += row['1-3 Días']; t2 += row['4-8 Días']; t3 += row['9+ Días']; total += row.total;
            });
            tableHtml += `<tr class="table-dark">
                <td class="ps-4 fw-bold">TOTAL GENERAL</td>
                <td class="text-center">${t1}</td>
                <td class="text-center">${t2}</td>
                <td class="text-center">${t3}</td>
                <td class="text-center fw-bold pe-4">${total}</td>
            </tr>`;
        }
        tableHtml += '</tbody></table>';
        container.innerHTML = tableHtml;
    }
    
    function renderizarGraficoMotivos(data) {
        const ctx = document.getElementById('chart-motivos');
        if (!ctx) return;
        if (chartMotivos) chartMotivos.destroy();
        
        chartMotivos = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.map(d => d.motivo),
                datasets: [{
                    label: 'Unidades',
                    data: data.map(d => d.total),
                    backgroundColor: 'rgba(13, 110, 253, 0.7)',
                    borderColor: '#0d6efd',
                    borderWidth: 2,
                    borderRadius: 5
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: { 
                    y: { beginAtZero: true, grid: { display: false }, ticks: { stepSize: 1 } },
                    x: { grid: { display: false } }
                }
            }
        });
    }

    function renderizarGraficoOperaciones(data) {
        const ctx = document.getElementById('chart-operaciones');
        if (!ctx) return;
        if (chartOperaciones) chartOperaciones.destroy();

        if (!data || data.length === 0) return;

        // Ordenamos para que los "Sin Clasificar" salgan al final
        data.sort((a, b) => b.total - a.total);

        const colors = [
            '#2ecc71', '#3498db', '#f1c40f', '#e67e22', '#9b59b6', 
            '#1abc9c', '#34495e', '#d35400', '#c0392b', '#7f8c8d'
        ];

        chartOperaciones = new Chart(ctx, {
            type: 'doughnut', 
            data: {
                labels: data.map(d => d.operacion),
                datasets: [{
                    data: data.map(d => d.total),
                    backgroundColor: colors.slice(0, data.length),
                    borderWidth: 0,
                    hoverOffset: 20
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { 
                        position: 'right',
                        labels: { 
                            boxWidth: 15, 
                            padding: 20, 
                            font: { size: 12 } 
                        }
                    }
                },
                onClick: (evt, elements) => {
                    if (elements.length > 0) {
                        const index = elements[0].index;
                        const selected = data[index];
                        mostrarDetalleOperacion({ operacion: selected.operacion, unidades: selected.unidades });
                    }
                }
            }
        });
    }

    // --- NUEVO: Gráfico para el Tipo de Vehículo ---
    function renderizarGraficoTipos(data) {
        const ctx = document.getElementById('chart-tipos');
        if (!ctx) return;
        if (chartTipos) chartTipos.destroy();

        if (!data || data.length === 0) return;

        data.sort((a, b) => b.total - a.total);

        // Colores distintivos (diferentes al de operaciones)
        const colors = ['#0dcaf0', '#6610f2', '#ffc107', '#dc3545', '#20c997', '#d63384'];

        chartTipos = new Chart(ctx, {
            type: 'pie', 
            data: {
                labels: data.map(d => d.tipo),
                datasets: [{
                    data: data.map(d => d.total),
                    backgroundColor: colors.slice(0, data.length),
                    borderWidth: 0,
                    hoverOffset: 20
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { 
                        position: 'right',
                        labels: { boxWidth: 15, padding: 20, font: { size: 12 } }
                    }
                },
                onClick: (evt, elements) => {
                    if (elements.length > 0) {
                        const index = elements[0].index;
                        const selected = data[index];
                        // Reutilizamos la misma vista dinámica de detalles, pasando el tipo como "operacion"
                        mostrarDetalleOperacion({ operacion: selected.tipo, unidades: selected.unidades });
                    }
                }
            }
        });
    }

    function mostrarDetalleOperacion(item) {
        const container = document.getElementById('detalle-operacion-container');
        const nameSpan = document.getElementById('op-selected-name');
        const unitsDiv = document.getElementById('op-selected-units');
        
        if (!container || !item) return;

        nameSpan.textContent = item.operacion;
        unitsDiv.innerHTML = '';
        
        // Mensaje de ayuda si es "Sin Clasificar"
        if (item.operacion.includes("Sin Clasificar") || item.operacion.includes("Sin Operación")) {
            const hint = document.createElement('div');
            hint.className = 'alert alert-warning w-100 text-center mb-3 small';
            hint.innerHTML = '<i class="bi bi-exclamation-triangle"></i> Estas unidades no tienen etiqueta en Samsara o el número económico registrado en taller no coincide exactamente con el de Samsara.';
            unitsDiv.appendChild(hint);
        }

        if (item.unidades && item.unidades.length > 0) {
            // Ordenar alfanumérico
            item.unidades.sort((a, b) => a.localeCompare(b, undefined, {numeric: true})).forEach(unit => {
                const badge = document.createElement('div');
                badge.className = 'badge bg-white text-dark border border-2 border-success p-3 shadow-sm';
                badge.style.minWidth = "100px";
                badge.style.fontSize = "1rem";
                badge.innerHTML = `<i class="bi bi-truck text-success me-2"></i> ${unit}`;
                unitsDiv.appendChild(badge);
            });
        } else {
            unitsDiv.innerHTML = '<p class="text-muted italic py-4">No hay datos de unidades específicas para esta categoría.</p>';
        }

        container.style.display = 'block';
        container.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

});