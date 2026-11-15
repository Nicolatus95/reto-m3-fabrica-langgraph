export default function FiltroDepartamento({ departamentos, valor, onCambio }) {
  return (
    <select
      data-testid="filtro-departamento"
      aria-label="Filtrar por departamento"
      value={valor}
      onChange={(e) => onCambio(e.target.value)}
      style={{ margin: '8px 0' }}
    >
      <option value="">Todos</option>
      {departamentos.map((d) => (
        <option key={d} value={d}>{d}</option>
      ))}
    </select>
  )
}
