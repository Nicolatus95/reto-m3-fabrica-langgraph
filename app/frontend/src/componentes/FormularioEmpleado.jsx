import React, { useState } from 'react'

const VACIO = { nombre: '', correo: '', puesto: '', departamento: '', fecha_ingreso: '' }

export default function FormularioEmpleado({ departamentos, alRegistrar }) {
  const [datos, setDatos] = useState(VACIO)
  const [exito, setExito] = useState('')
  const [error, setError] = useState('')

  const cambiar = (campo) => (e) => setDatos({ ...datos, [campo]: e.target.value })

  const enviar = async (e) => {
    e.preventDefault()
    setExito('')
    setError('')
    const cuerpo = { ...datos }
    if (!cuerpo.fecha_ingreso) delete cuerpo.fecha_ingreso
    try {
      const r = await fetch('/api/empleados', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cuerpo),
      })
      const json = await r.json().catch(() => ({}))
      if (r.status === 201) {
        setExito(`Empleado registrado con número ${json.numero_empleado}`)
        setDatos(VACIO)
        await alRegistrar()
      } else if (json.campo) {
        setError(`Corrige el campo: ${json.campo}`)
      } else {
        setError(json.detail || 'No se pudo registrar al empleado')
      }
    } catch {
      setError('No se pudo conectar con el servidor')
    }
  }

  return (
    <form onSubmit={enviar} noValidate style={{ display: 'grid', gap: 8, marginBottom: 24 }}>
      <h2>Registrar empleado</h2>
      <label>
        Nombre
        <input data-testid="empleado-nombre" value={datos.nombre} onChange={cambiar('nombre')} />
      </label>
      <label>
        Correo
        <input data-testid="empleado-correo" value={datos.correo} onChange={cambiar('correo')} />
      </label>
      <label>
        Puesto
        <input data-testid="empleado-puesto" value={datos.puesto} onChange={cambiar('puesto')} />
      </label>
      <label>
        Departamento
        <select
          data-testid="empleado-departamento"
          value={datos.departamento}
          onChange={cambiar('departamento')}
        >
          <option value="">Selecciona...</option>
          {departamentos.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
      </label>
      <label>
        Fecha de ingreso
        <input
          type="date"
          data-testid="empleado-fecha-ingreso"
          value={datos.fecha_ingreso}
          onChange={cambiar('fecha_ingreso')}
        />
      </label>
      <button type="submit" data-testid="empleado-guardar">
        Guardar
      </button>
      {exito && (
        <p data-testid="mensaje-exito" style={{ color: 'green' }}>
          {exito}
        </p>
      )}
      {error && (
        <p data-testid="mensaje-error" style={{ color: 'crimson' }}>
          {error}
        </p>
      )}
    </form>
  )
}
