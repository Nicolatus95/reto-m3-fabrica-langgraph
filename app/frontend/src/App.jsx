import React, { useCallback, useEffect, useState } from 'react'
import FormularioEmpleado from './componentes/FormularioEmpleado.jsx'
import TablaEmpleados from './componentes/TablaEmpleados.jsx'
import BuscadorEmpleados from './componentes/BuscadorEmpleados.jsx'
import FiltroDepartamento from './componentes/FiltroDepartamento.jsx'
import FormularioEdicion from './componentes/FormularioEdicion.jsx'
import FormularioBaja from './componentes/FormularioBaja.jsx'
import { listarEmpleados, editarEmpleado, darDeBajaEmpleado } from './api.js'

export default function App() {
  const [departamentos, setDepartamentos] = useState([])
  const [empleados, setEmpleados] = useState([])

  const [editando, setEditando] = useState(null)
  const [dandoBaja, setDandoBaja] = useState(null)
  const [mensaje, setMensaje] = useState(null)
  const [claveFormulario, setClaveFormulario] = useState(0)

  const [buscar, setBuscar] = useState('')
  const [departamento, setDepartamento] = useState('')

  const cargarEmpleados = useCallback(async () => {
    try {
      setEmpleados(await listarEmpleados({ buscar, departamento }))
    } catch {
      // se conserva la lista actual si falla la carga
    }
  }, [buscar, departamento])

  useEffect(() => {
    fetch('/api/departamentos')
      .then((r) => r.json())
      .then(setDepartamentos)
      .catch(() => setDepartamentos([]))
  }, [])

  useEffect(() => {
    const espera = setTimeout(cargarEmpleados, 250)
    return () => clearTimeout(espera)
  }, [cargarEmpleados])

  const abrirEdicion = (e) => {
    setMensaje(null)
    setDandoBaja(null)
    setEditando(e)
  }

  const abrirBaja = (e) => {
    setMensaje(null)
    setEditando(null)
    setDandoBaja(e)
  }

  const cancelar = () => {
    setEditando(null)
    setDandoBaja(null)
    setMensaje(null)
  }

  const guardarEdicion = async (id, datos) => {
    setMensaje(null)
    try {
      await editarEmpleado(id, datos)
      setEditando(null)
      setMensaje({ tipo: 'exito', texto: 'Empleado actualizado correctamente' })
      setClaveFormulario((k) => k + 1)
      await cargarEmpleados()
    } catch (err) {
      setMensaje({ tipo: 'error', texto: err.message || 'No se pudo editar al empleado' })
    }
  }

  const confirmarBaja = async (id, fecha) => {
    setMensaje(null)
    try {
      await darDeBajaEmpleado(id, fecha)
      setDandoBaja(null)
      setMensaje({ tipo: 'exito', texto: 'Empleado dado de baja correctamente' })
      setClaveFormulario((k) => k + 1)
      await cargarEmpleados()
    } catch (err) {
      setMensaje({ tipo: 'error', texto: err.message || 'No se pudo dar de baja al empleado' })
    }
  }

  const hayPanel = editando || dandoBaja

  return (
    <main style={{ fontFamily: 'sans-serif', maxWidth: 960, margin: '0 auto', padding: 16 }}>
      <h1>Gestión de empleados</h1>
      {!hayPanel && (
        <FormularioEmpleado key={claveFormulario} departamentos={departamentos} alRegistrar={cargarEmpleados} />
      )}
      {editando && (
        <FormularioEdicion
          empleado={editando}
          departamentos={departamentos}
          onGuardar={guardarEdicion}
          onCancelar={cancelar}
        />
      )}
      {dandoBaja && (
        <FormularioBaja empleado={dandoBaja} onConfirmar={confirmarBaja} onCancelar={cancelar} />
      )}
      {mensaje && (
        <p
          data-testid={mensaje.tipo === 'exito' ? 'mensaje-exito' : 'mensaje-error'}
          style={{ color: mensaje.tipo === 'exito' ? 'green' : 'crimson' }}
        >
          {mensaje.texto}
        </p>
      )}
      <BuscadorEmpleados valor={buscar} onCambio={setBuscar} />
      <FiltroDepartamento departamentos={departamentos} valor={departamento} onCambio={setDepartamento} />
      <TablaEmpleados empleados={empleados} alEditar={abrirEdicion} alBaja={abrirBaja} />
    </main>
  )
}
