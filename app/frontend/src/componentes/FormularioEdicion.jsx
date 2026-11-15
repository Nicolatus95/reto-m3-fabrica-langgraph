import React, { useState } from 'react'

export default function FormularioEdicion({ empleado, departamentos, onGuardar, onCancelar }) {
  const [puesto, setPuesto] = useState(empleado.puesto)
  const [departamento, setDepartamento] = useState(empleado.departamento)

  function enviar(e) {
    e.preventDefault()
    onGuardar(empleado.id, { puesto, departamento })
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
      <button type="submit" data-testid="empleado-guardar">Guardar</button>
      <button type="button" onClick={onCancelar}>Cancelar</button>
    </form>
  )
}
