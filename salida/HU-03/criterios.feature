# language: es
Característica: Editar y dar de baja a un empleado
  Como persona del área de Recursos Humanos
  quiero cambiar el puesto y el departamento de un empleado, y poder darlo de baja
  para mantener el directorio al día sin perder el historial

  Escenario: Editar puesto y departamento de un empleado activo
    Dado un empleado activo con número "EMP-0001", correo "ana.lopez@empresa.com", puesto "Analista" y departamento "Ventas"
    Cuando Recursos Humanos cambia el puesto a "Líder de Finanzas" y el departamento a "Finanzas"
    Entonces la respuesta es 200 y el empleado "EMP-0001" muestra puesto "Líder de Finanzas" y departamento "Finanzas"
    Y el número de empleado "EMP-0001" y el correo "ana.lopez@empresa.com" no cambian
    Y el estado sigue siendo "activo"

  Escenario: Rechazar un departamento fuera de la lista permitida
    Dado un empleado activo con número "EMP-0002" y departamento "Ventas"
    Cuando Recursos Humanos cambia el departamento a "Marketing"
    Entonces la respuesta es 422 y la pantalla indica que se debe corregir el campo "departamento"
    Y el empleado "EMP-0002" conserva el departamento "Ventas"

  Escenario: Rechazar un puesto de un solo carácter
    Dado un empleado activo con número "EMP-0003" y puesto "Analista"
    Cuando Recursos Humanos cambia el puesto a "A"
    Entonces la respuesta es 422 y la pantalla indica que se debe corregir el campo "puesto"
    Y el empleado "EMP-0003" conserva el puesto "Analista"

  Escenario: Rechazar un puesto de más de 60 caracteres
    Dado un empleado activo con número "EMP-0004" y puesto "Analista"
    Cuando Recursos Humanos cambia el puesto a un texto de 61 caracteres
    Entonces la respuesta es 422 y la pantalla indica que se debe corregir el campo "puesto"
    Y el empleado "EMP-0004" conserva el puesto "Analista"

  Escenario: Dar de baja a un empleado activo
    Dado un empleado activo con número "EMP-0005", fecha de ingreso "2024-03-01"
    Cuando Recursos Humanos da de baja al empleado "EMP-0005" con fecha de baja "2026-10-15"
    Entonces la respuesta es 200 y el empleado "EMP-0005" tiene estado "baja" y fecha de baja "2026-10-15"
    Y el empleado "EMP-0005" sigue apareciendo en el directorio marcado como "Baja"

  Escenario: Rechazar una fecha de baja anterior a la fecha de ingreso
    Dado un empleado activo con número "EMP-0006", fecha de ingreso "2024-03-01"
    Cuando Recursos Humanos da de baja al empleado "EMP-0006" con fecha de baja "2024-02-28"
    Entonces la respuesta es 422 y la pantalla indica que se debe corregir el campo "fecha_baja"
    Y el empleado "EMP-0006" sigue con estado "activo" y sin fecha de baja

  Escenario: No se puede editar a un empleado dado de baja
    Dado un empleado con número "EMP-0007" en estado "baja" y puesto "Analista"
    Cuando Recursos Humanos cambia el puesto a "Gerente"
    Entonces la respuesta es 409 con el mensaje "No se puede editar a un empleado dado de baja"
    Y el empleado "EMP-0007" conserva el puesto "Analista"

# Preguntas abiertas
# - ¿La fecha de baja la captura Recursos Humanos o el sistema usa la fecha de hoy? Se asumió que se captura.
# - ¿Qué responde el sistema si se intenta modificar el correo o el número de empleado (error 422, o se ignora el cambio)? No hay mensaje definido.
# - ¿Qué pasa al dar de baja a un empleado que ya está en baja (respuesta y mensaje)?
# - ¿Puede la fecha de baja ser futura?
# - ¿Se puede editar solo uno de los dos campos (puesto o departamento) en una misma petición?
# - ¿Qué respuesta se da al editar o dar de baja un empleado que no existe (404)?
