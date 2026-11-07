import { useCallback, useEffect, useState } from 'react';
import EventCard from './components/EventCard.jsx';
import SignupForm from './components/SignupForm.jsx';
import MyRegistrations from './components/MyRegistrations.jsx';
import { mensajeErrorApi } from './util.js';
import { API_URL } from './config.js';

export default function App() {
  const [estado, setEstado] = useState('cargando'); // cargando | listo | error
  const [eventos, setEventos] = useState([]);
  const [mensaje, setMensaje] = useState('');
  const [eventoElegido, setEventoElegido] = useState('');

  const cargarEventos = useCallback(async () => {
    setEstado('cargando');
    try {
      const r = await fetch(`${API_URL}/eventos`);
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw Object.assign(new Error('api'), { data });
      setEventos(data);
      setEstado('listo');
    } catch (error) {
      setMensaje(mensajeErrorApi(error, error.data));
      setEstado('error');
    }
  }, []);

  useEffect(() => {
    cargarEventos();
  }, [cargarEventos]);

  function inscribirme(eventoId) {
    setEventoElegido(eventoId);
    document.getElementById('inscripcion')?.scrollIntoView({ behavior: 'smooth' });
  }

  return (
    <div className="pagina">
      <header className="encabezado">
        <h1>Eventos UM</h1>
        <p className="subtitulo">
          Consultá los eventos, inscribite y recibí la confirmación y un recordatorio por correo.
        </p>
      </header>

      <main>
        <section className="seccion" aria-labelledby="titulo-eventos">
          <h2 id="titulo-eventos">Próximos eventos</h2>
          {estado === 'cargando' && <p className="aviso">Cargando eventos…</p>}
          {estado === 'error' && (
            <div>
              <p className="aviso error" role="alert">{mensaje}</p>
              <button type="button" onClick={cargarEventos}>Reintentar</button>
            </div>
          )}
          {estado === 'listo' && eventos.length === 0 && (
            <p className="aviso">No hay eventos programados por ahora.</p>
          )}
          {estado === 'listo' && eventos.length > 0 && (
            <div className="grilla-eventos">
              {eventos.map((ev) => (
                <EventCard key={ev.eventoId} evento={ev} onInscribirme={inscribirme} />
              ))}
            </div>
          )}
        </section>

        <section className="seccion" id="inscripcion" aria-labelledby="titulo-inscripcion">
          <h2 id="titulo-inscripcion">Inscribirse</h2>
          <SignupForm
            eventos={eventos}
            eventoElegido={eventoElegido}
            onInscripcionExitosa={cargarEventos}
          />
        </section>

        <section className="seccion" aria-labelledby="titulo-mis">
          <h2 id="titulo-mis">Mis inscripciones</h2>
          <MyRegistrations />
        </section>
      </main>

      <footer className="pie">
        <p>Universidad de Montevideo · Sistemas en la Nube · aws-eventos-um</p>
      </footer>
    </div>
  );
}