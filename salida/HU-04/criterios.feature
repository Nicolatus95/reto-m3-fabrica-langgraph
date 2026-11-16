# language: es
Característica: Asignar jefe directo a un empleado
  Como persona de Recursos Humanos
  quiero asignar a cada empleado su jefe directo
  para conocer la línea de reporte

  Escenario: Asignar como jefe a un empleado activo
    Dado un empleado activo "Ana Pérez" con número "EMP-0001" y un empleado activo "Luis Gómez" con número "EMP-0002" sin jefe
    Cuando la persona de Recursos Humanos asigna a "Ana Pérez" como jefe de "Luis Gómez"
    Entonces el empleado "Luis Gómez" queda con jefe_id igual al id de "Ana Pérez" y la API responde 200

  Escenario: Ver el nombre del jefe en el directorio
    Dado un empleado activo "Luis Gómez" cuyo jefe es el empleado activo "Ana Pérez"
    Cuando la persona abre el directorio de empleados
    Entonces la fila de "Luis Gómez" muestra el nombre "Ana Pérez" como su jefe

  Escenario: Quitar el jefe de un empleado
    Dado un empleado activo "Luis Gómez" cuyo jefe es el empleado activo "Ana Pérez"
    Cuando la persona quita el jefe de "Luis Gómez"
    Entonces el empleado "Luis Gómez" queda con jefe_id vacío, la API responde 200 y el directorio no muestra jefe en su fila

  Escenario: Rechazar que un empleado sea su propio jefe
    Dado un empleado activo "Ana Pérez" con número "EMP-0001"
    Cuando la persona asigna a "Ana Pérez" como jefe de "Ana Pérez"
    Entonces la API responde 422 con el mensaje "Un empleado no puede ser su propio jefe" y el jefe de "Ana Pérez" no cambia

  Escenario: Rechazar un jefe que no existe
    Dado un empleado activo "Luis Gómez" sin jefe y que no existe ningún empleado con id 9999
    Cuando la persona asigna el empleado con id 9999 como jefe de "Luis Gómez"
    Entonces la API responde 422 con el mensaje "El jefe indicado no existe" y "Luis Gómez" sigue sin jefe

  Escenario: Rechazar un jefe dado de baja
    Dado un empleado activo "Luis Gómez" sin jefe y un empleado "Marta Ruiz" con estado "baja"
    Cuando la persona asigna a "Marta Ruiz" como jefe de "Luis Gómez"
    Entonces la API responde 409 con el mensaje "Un empleado dado de baja no puede ser jefe" y "Luis Gómez" sigue sin jefe

  Escenario: Rechazar un ciclo directo en la línea de reporte
    Dado un empleado activo "Ana Pérez" y un empleado activo "Luis Gómez" cuyo jefe es "Ana Pérez"
    Cuando la persona asigna a "Luis Gómez" como jefe de "Ana Pérez"
    Entonces la API responde 422 con el mensaje "La asignación crearía un ciclo en la línea de reporte" y "Ana Pérez" sigue sin jefe

  Escenario: Rechazar un ciclo indirecto en la línea de reporte
    Dado tres empleados activos "Ana Pérez", "Luis Gómez" y "Eva Soto" donde "Luis Gómez" reporta a "Ana Pérez" y "Eva Soto" reporta a "Luis Gómez"
    Cuando la persona asigna a "Eva Soto" como jefe de "Ana Pérez"
    Entonces la API responde 422 con el mensaje "La asignación crearía un ciclo en la línea de reporte" y "Ana Pérez" sigue sin jefe

  Escenario: Al dar de baja a un jefe sus subordinados quedan sin jefe
    Dado un empleado activo "Ana Pérez" que es jefe de los empleados activos "Luis Gómez" y "Eva Soto"
    Cuando la persona da de baja a "Ana Pérez"
    Entonces "Ana Pérez" queda con estado "baja" y los empleados "Luis Gómez" y "Eva Soto" quedan con jefe_id vacío

# Preguntas abiertas
# - ¿Qué se muestra en la columna de jefe del directorio cuando el empleado no tiene jefe (vacío, guion u otro texto)?
# - ¿Se puede asignar o quitar el jefe de un empleado dado de baja? La regla 6 impide editarlo (409 «No se puede editar a un empleado dado de baja»), pero la historia no lo menciona.
# - ¿Cuál es el endpoint o la acción de pantalla exacta para asignar y quitar el jefe (campo en la edición del empleado o acción aparte)?
# - ¿El selector de jefe en pantalla debe listar solo empleados activos, o se muestran todos y se rechaza al guardar?
# - Si una asignación vuelve a poner el mismo jefe que ya tenía el empleado, ¿se acepta sin cambios?
