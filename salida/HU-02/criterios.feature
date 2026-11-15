# language: es
Característica: Consultar el directorio de empleados
  Como persona del área de Recursos Humanos
  quiero ver el directorio, buscar por nombre o correo y filtrar por departamento
  para encontrar rápido a una persona

  Escenario: Ver el directorio con los datos de cada empleado
    Dado que existen los empleados "EMP-0001 Ana Torres, Analista, Tecnología, activo" y "EMP-0002 Luis Pérez, Vendedor, Ventas, activo"
    Cuando abro la pantalla del directorio
    Entonces veo una fila para "EMP-0001" con nombre "Ana Torres", puesto "Analista", departamento "Tecnología" y estado "activo"
    Y veo una fila para "EMP-0002" con nombre "Luis Pérez", puesto "Vendedor", departamento "Ventas" y estado "activo"

  Escenario: Buscar por nombre sin distinguir mayúsculas de minúsculas
    Dado que existen los empleados "Ana Torres" con correo "ana.torres@empresa.com" y "Luis Pérez" con correo "luis.perez@empresa.com"
    Cuando escribo "ANA TORRES" en el buscador
    Entonces veo solo la fila de "Ana Torres"
    Y no veo la fila de "Luis Pérez"

  Escenario: Buscar por correo sin distinguir mayúsculas de minúsculas
    Dado que existen los empleados "Ana Torres" con correo "ana.torres@empresa.com" y "Luis Pérez" con correo "luis.perez@empresa.com"
    Cuando escribo "Luis.Perez@Empresa.COM" en el buscador
    Entonces veo solo la fila de "Luis Pérez"
    Y no veo la fila de "Ana Torres"

  Escenario: Filtrar por departamento
    Dado que existen los empleados "Ana Torres" en "Tecnología", "Luis Pérez" en "Ventas" y "Marta Gil" en "Tecnología"
    Cuando selecciono el departamento "Tecnología" en el filtro
    Entonces veo las filas de "Ana Torres" y "Marta Gil"
    Y no veo la fila de "Luis Pérez"

  Escenario: Búsqueda sin resultados muestra un mensaje
    Dado que existen los empleados "Ana Torres" y "Luis Pérez"
    Cuando escribo "Zacarías" en el buscador
    Entonces no veo ninguna fila de empleados
    Y veo un mensaje que indica que no hay resultados

  Escenario: Filtro por departamento sin empleados muestra un mensaje
    Dado que existen los empleados "Ana Torres" en "Tecnología" y "Luis Pérez" en "Ventas"
    Cuando selecciono el departamento "Finanzas" en el filtro
    Entonces no veo ninguna fila de empleados
    Y veo un mensaje que indica que no hay resultados

  Escenario: Un empleado dado de baja sigue apareciendo en el directorio
    Dado que existe el empleado "EMP-0003 Marta Gil" con estado "baja" y fecha de baja "2026-03-15"
    Cuando abro la pantalla del directorio
    Entonces veo una fila para "EMP-0003" con nombre "Marta Gil" y estado "baja"

# Preguntas abiertas
# - ¿La búsqueda es por coincidencia parcial (contiene) o por texto completo? Se asumió solo en los ejemplos de texto completo.
# - ¿Se pueden combinar búsqueda y filtro de departamento a la vez (ambos aplicados)?
# - ¿Cuál es el texto exacto del mensaje cuando no hay resultados?
# - ¿Cuál es el orden del listado (por número de empleado, por nombre)?
# - ¿Hay paginación si el directorio es grande?
# - ¿Qué se muestra si el directorio está completamente vacío (sin empleados registrados)?
# - ¿La búsqueda ignora acentos (por ejemplo "Perez" frente a "Pérez")?
