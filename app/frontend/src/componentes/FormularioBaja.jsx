import { useState } from 'react'

export default function FormularioBaja({ empleado, onConfirmar, onCancelar }) {
  const [fecha, setFecha] = useState('')

  function enviar(e) {
    e.preventDefault()
    onConfirmar(empleado.id, fecha)
  }

  return (
    <form onSubmit={enviar} noValidate style={{ display: 'grid', gap: 8, maxWidth: 400 }}>
      <h2>Dar de baja a {empleado.nombre}</h2>
      <label>
        Fecha de baja
        <input
          type="date"
          data-testid="empleado-fecha-baja"
          value={fecha}
          onChange={(e) => setFecha(e.target.value)}
        />
      </label>
      <button type="submit" data-testid="confirmar-baja">Confirmar baja</button>
      <button type="button" onClick={onCancelar}>Cancelar</button>
    </form>
  )
}
