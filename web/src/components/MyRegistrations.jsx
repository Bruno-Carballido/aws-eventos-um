import { useState } from 'react';
import { formatearFecha, validarEmail, mensajeErrorApi } from '../util.js';
import { API_URL } from '../config.js';

export default function MyRegistrations() {
  const [email, setEmail] = useState('');
  const [estado, setEstado] = useState('idle'); // idle | buscando | listo | vacio | error
  const [inscripciones, setInscripciones] = useState([]);
  const [mensaje, setMensaje] = useState('');

  async function buscar(ev) {
    ev.preventDefault();
    if (!validarEmail(email)) {
      setEstado('error');
      setMensaje('Ingresá un email válido para buscar tus inscripciones.');
      return;
    }
    setEstado('buscando');
    setMensaje('');
    try {
      const r = await fetch(
        `${API_URL}/inscripciones?email=${encodeURIComponent(email.trim().toLowerCase())}`,
      );
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        setEstado('error');
        setMensaje(mensajeErrorApi(null, data));
        return;
      }
      setInscripciones(data);
      setEstado(data.length ? 'listo' : 'vacio');
    } catch (error) {
      setEstado('error');
      setMensaje(mensajeErrorApi(error));
    }
  }

  return (
    <section className="seccion">
      <form className="formulario fila" onSubmit={buscar} noValidate>
        <div className="campo">
          <label htmlFor="email-consulta">Email con el que te inscribiste</label>
          <input
            id="email-consulta"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="tu@email.com"
          />
        </div>
        <button type="submit" disabled={estado === 'buscando'}>
          {estado === 'buscando' ? 'Buscando…' : 'Buscar'}
        </button>
      </form>

      {estado === 'error' && <p className="aviso error" role="alert">{mensaje}</p>}
      {estado === 'vacio' && (
        <p className="aviso">
          No encontramos inscripciones para ese email. ¿Todavía no te inscribiste?
        </p>
      )}

      {estado === 'listo' && (
        <ul className="lista-inscripciones">
          {inscripciones.map((insc) => (
            <li key={insc.inscripcionId} className="item-inscripcion">
              <strong>{insc.tituloEvento || insc.eventoId}</strong>
              <span className="meta">Inscripción registrada el {formatearFecha(insc.creadoEn)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}