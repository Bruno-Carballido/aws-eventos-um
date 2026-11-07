import { formatearFecha, cuposDe } from '../util.js';

export default function EventCard({ evento, onInscribirme }) {
  const cupos = cuposDe(evento);

  return (
    <article className="tarjeta-evento">
      <h3>{evento.titulo}</h3>
      <p className="meta">
        <span aria-hidden="true">📅</span> {formatearFecha(evento.fecha)}
      </p>
      <p className="meta">
        <span aria-hidden="true">📍</span> {evento.lugar || 'Lugar a confirmar'}
      </p>
      {evento.descripcion && <p className="descripcion">{evento.descripcion}</p>}
      <div className="pie-tarjeta">
        <span className={`cupos ${cupos.clase}`}>
          {cupos.cupo == null
            ? 'Cupo libre'
            : cupos.lleno
              ? 'Sin lugares disponibles'
              : `${cupos.inscritos}/${cupos.cupo} lugares`}
        </span>
        <button
          type="button"
          onClick={() => onInscribirme(evento.eventoId)}
          disabled={cupos.lleno}
        >
          {cupos.lleno ? 'Completo' : 'Inscribirme'}
        </button>
      </div>
    </article>
  );
}