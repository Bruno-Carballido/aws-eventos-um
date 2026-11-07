import { useEffect, useState } from 'react';
import { cuposDe, validarEmail, mensajeErrorApi } from '../util.js';
import { API_URL } from '../config.js';

export default function SignupForm({ eventos, eventoElegido, onInscripcionExitosa }) {
  const [eventoId, setEventoId] = useState(eventoElegido || '');
  const [nombre, setNombre] = useState('');
  const [email, setEmail] = useState('');
  const [errores, setErrores] = useState({});
  const [estado, setEstado] = useState('idle'); // idle | enviando | exito | error
  const [mensaje, setMensaje] = useState('');

  useEffect(() => {
    if (eventoElegido) setEventoId(eventoElegido);
  }, [eventoElegido]);

  function validar() {
    const errs = {};
    if (!eventoId) errs.eventoId = 'Elegí un evento.';
    if (!nombre.trim()) errs.nombre = 'Ingresá tu nombre.';
    if (!email.trim()) errs.email = 'Ingresá tu email.';
    else if (!validarEmail(email)) errs.email = 'El email no tiene un formato válido.';
    setErrores(errs);
    return Object.keys(errs).length === 0;
  }

  async function enviar(ev) {
    ev.preventDefault();
    if (!validar()) return;
    setEstado('enviando');
    setMensaje('');
    try {
      const r = await fetch(`${API_URL}/inscripciones`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ eventoId, nombre, email }),
      });
      const data = await r.json().catch(() => ({}));
      if (r.ok) {
        setEstado('exito');
        setMensaje('¡Inscripción registrada! Revisá tu correo para la confirmación.');
        setNombre('');
        setEmail('');
        onInscripcionExitosa();
      } else {
        setEstado('error');
        setMensaje(mensajeErrorApi(null, data));
      }
    } catch (error) {
      setEstado('error');
      setMensaje(mensajeErrorApi(error));
    }
  }

  return (
    <form className="formulario" onSubmit={enviar} noValidate>
      <div className="campo">
        <label htmlFor="eventoId">Evento</label>
        <select
          id="eventoId"
          value={eventoId}
          onChange={(e) => setEventoId(e.target.value)}
        >
          <option value="">Elegí un evento…</option>
          {eventos.map((ev) => {
            const cupos = cuposDe(ev);
            return (
              <option key={ev.eventoId} value={ev.eventoId} disabled={cupos.lleno}>
                {ev.titulo}{cupos.lleno ? ' (completo)' : ''}
              </option>
            );
          })}
        </select>
        {errores.eventoId && <span className="error-campo">{errores.eventoId}</span>}
      </div>

      <div className="campo">
        <label htmlFor="nombre">Nombre</label>
        <input
          id="nombre"
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          placeholder="Tu nombre"
        />
        {errores.nombre && <span className="error-campo">{errores.nombre}</span>}
      </div>

      <div className="campo">
        <label htmlFor="email">Email</label>
        <input
          id="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="tu@email.com"
        />
        {errores.email && <span className="error-campo">{errores.email}</span>}
      </div>

      <button type="submit" disabled={estado === 'enviando'}>
        {estado === 'enviando' ? 'Enviando…' : 'Inscribirme'}
      </button>

      {estado === 'exito' && <p className="aviso exito" role="status">{mensaje}</p>}
      {estado === 'error' && <p className="aviso error" role="alert">{mensaje}</p>}
    </form>
  );
}