export function formatearFecha(fechaISO) {
  if (!fechaISO) return 'Fecha a confirmar';
  const f = new Date(fechaISO);
  return f.toLocaleDateString('es-UY', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

export function cuposDe(evento) {
  const cupo = evento.cupo ?? null;
  const inscritos = evento.inscritos ?? 0;
  const lleno = cupo != null && inscritos >= cupo;
  let clase = 'cupos-verde';
  if (lleno) clase = 'cupos-rojo';
  else if (cupo != null && inscritos >= cupo * 0.5) clase = 'cupos-ambar';
  return { cupo, inscritos, lleno, clase };
}

export function validarEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
}

export function mensajeErrorApi(error, respuesta) {
  if (respuesta && respuesta.error) return respuesta.error;
  if (error instanceof TypeError) {
    return 'No se pudo conectar con la API. Revisá que API_URL esté configurada en src/config.js.';
  }
  return 'Ocurrió un error inesperado. Intentá de nuevo.';
}