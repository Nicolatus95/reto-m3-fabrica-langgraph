import React from 'react'

export default function TablaEmpleados({ empleados, alEditar, alBaja }) {
  return (
    <section>
      <h2>Directorio</h2>
      <table data-testid="tabla-empleados" border="1" cellPadding="6" style={{ borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            <th>Número</th>
            <th>Nombre</th>
            <th>Correo</th>
            <th>Puesto</th>
            <th>Departamento</th>
            <th>Fecha de ingreso</th>
            <th>Estado</th>
            <th>Acciones</th>
          </tr>
        </thead>
        <tbody>
          {empleados.map((e) => (
            <tr key={e.id} data-testid={`fila-empleado-${e.id}`}>
              <td data-testid={`numero-empleado-${e.id}`}>{e.numero_empleado}</td>
              <td>{e.nombre}</td>
              <td>{e.correo}</td>
              <td>{e.puesto}</td>
              <td>{e.departamento}</td>
              <td>{e.fecha_ingreso}</td>
              <td data-testid={`estado-empleado-${e.id}`}>{e.estado === 'baja' ? 'Baja' : 'Activo'}</td>
              <td>
                <button type="button" data-testid={`editar-empleado-${e.id}`} onClick={() => alEditar && alEditar(e)}>
                  Editar
                </button>{' '}
                {e.estado !== 'baja' && (
                  <button type="button" data-testid={`baja-empleado-${e.id}`} onClick={() => alBaja && alBaja(e)}>
                    Dar de baja
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {empleados.length === 0 && <p data-testid="sin-resultados">No se encontraron empleados</p>}
    </section>
  )
}
