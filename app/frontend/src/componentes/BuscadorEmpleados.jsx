export default function BuscadorEmpleados({ valor, onCambio }) {
  return (
    <input
      data-testid="buscar-empleados"
      placeholder="Buscar por nombre, correo o número"
      value={valor}
      onChange={(e) => onCambio(e.target.value)}
      style={{ margin: '8px 0', width: '100%', maxWidth: 400 }}
    />
  )
}
