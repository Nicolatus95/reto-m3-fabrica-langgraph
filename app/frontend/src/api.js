// Funciones de acceso a la API (rutas relativas)
async function pedir(url, opciones) {
  const respuesta = await fetch(url, opciones)
  let cuerpo = null
  try {
    cuerpo = await respuesta.json()
  } catch {
    cuerpo = null
  }
  if (!respuesta.ok) {
    const detalle = cuerpo && typeof cuerpo.detail === 'string' ? cuerpo.detail : 'Ocurrió un error'
    throw new Error(detalle)
  }
  return cuerpo
}

export function listarEmpleados({ buscar = '', departamento = '' } = {}) {
  const partes = []
  if (buscar) partes.push(`buscar=${encodeURIComponent(buscar)}`)
  if (departamento) partes.push(`departamento=${encodeURIComponent(departamento)}`)
  const parametros = partes.length ? `?${partes.join('&')}` : ''
  return pedir(`/api/empleados${parametros}`)
}

export function listarDepartamentos() {
  return pedir('/api/departamentos')
}

export function editarEmpleado(id, datos) {
  return pedir(`/api/empleados/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(datos),
  })
}

export function darDeBajaEmpleado(id, fecha_baja) {
  return pedir(`/api/empleados/${id}/baja`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ fecha_baja }),
  })
}

export function crearEmpleado(datos) {
  return pedir('/api/empleados', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(datos),
  })
}
