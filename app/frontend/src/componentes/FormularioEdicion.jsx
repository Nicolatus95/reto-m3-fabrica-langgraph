import React, { useState } from 'react'

export default function FormularioEdicion({ empleado, departamentos, onGuardar, onCancelar, candidatos = [] }) {
  const [jefeId, setJefeId] = useState(empleado.jefe_id == null ? '' : String(empleado.jefe_id))
  const [puesto, setPuesto] = useState(empleado.puesto)
  const [departamento, setDepartamento] = useState(empleado.departamento)

  function enviar(e) {
    e.preventDefault()
    onGuardar(empleado.id, { puesto, departamento, jefe_id: jefeId ? Number(jefeId) : null })
  }

  return (
    <form onSubmit={enviar} noValidate style={{ display: 'grid', gap: 8, maxWidth: 400 }}>
      <h2>Editar a {empleado.nombre}</h2>
      <label>
        Puesto
        <input data-testid="empleado-puesto" value={puesto} onChange={(e) => setPuesto(e.target.value)} />
      </label>
      <label>
        Departamento
        <select
          data-testid="empleado-departamento"
          value={departamento}
          onChange={(e) => setDepartamento(e.target.value)}
        >
          {departamentos.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
      </label>
      <label>
        Jefe
        <select data-testid="empleado-jefe" value={jefeId} onChange={(e) => setJefeId(e.target.value)}>
          <option value="">Sin jefe</option>
          {candidatos
            .filter((c) => c.id !== empleado.id)
            .map((c) => (
              <option key={c.id} value={String(c.id)}>
                {c.nombre}
              </option>
            ))}
        </select>
      </label>
      <button type="submit" data-testid="empleado-guardar">Guardar</button>
      <button type="button" onClick={onCancelar}>Cancelar</button>
    </form>
  )
}
