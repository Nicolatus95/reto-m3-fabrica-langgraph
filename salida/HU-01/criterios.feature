# language: es
Característica: Registrar empleado
  Como persona del área de Recursos Humanos
  quiero registrar a un empleado con nombre, correo corporativo, puesto, departamento y fecha de ingreso
  para darlo de alta en la empresa

  Escenario: Registro exitoso con número de empleado asignado por el sistema
    Dado que no existe ningún empleado registrado
    Cuando registro a "Ana Torres" con correo "ana.torres@empresa.com", puesto "Analista", departamento "Finanzas" y fecha de ingreso "2024-03-15"
    Entonces el sistema responde 201 y muestra un mensaje de confirmación con el número de empleado "EMP-0001"
    Y el empleado queda guardado con estado "activo" y una fecha y hora de creación asignada por el sistema

  Escenario: El número de empleado es consecutivo
    Dado que existe un empleado con número "EMP-0001"
    Cuando registro a "Luis Pérez" con correo "luis.perez@empresa.com", puesto "Ejecutivo de ventas", departamento "Ventas" y fecha de ingreso "2024-05-02"
    Entonces el sistema responde 201 y muestra un mensaje de confirmación con el número de empleado "EMP-0002"

  Escenario: El correo se guarda en minúsculas
    Dado que no existe ningún empleado con correo "marta.ruiz@empresa.com"
    Cuando registro a "Marta Ruiz" con correo "Marta.Ruiz@Empresa.com", puesto "Desarrolladora", departamento "Tecnología" y fecha de ingreso "2024-01-10"
    Entonces el sistema responde 201
    Y el empleado queda guardado con correo "marta.ruiz@empresa.com"

  Escenario: Correo duplicado sin importar mayúsculas
    Dado que existe un empleado con correo "ana.torres@empresa.com"
    Cuando registro a "Ana Torres Díaz" con correo "ANA.TORRES@empresa.com", puesto "Contadora", departamento "Finanzas" y fecha de ingreso "2024-06-01"
    Entonces el sistema responde 409 con el mensaje "El correo ya está registrado"
    Y no se crea ningún empleado nuevo

  Escenario: Correo que no es del dominio corporativo
    Dado que no existe ningún empleado con correo "ana.torres@gmail.com"
    Cuando registro a "Ana Torres" con correo "ana.torres@gmail.com", puesto "Analista", departamento "Finanzas" y fecha de ingreso "2024-03-15"
    Entonces el sistema responde 422 con el mensaje "Usa el correo corporativo @empresa.com"
    Y no se crea ningún empleado nuevo

  Escenario: Fecha de ingreso futura
    Dado que la fecha de ingreso "2099-01-01" es posterior a la fecha actual
    Cuando registro a "Pedro Gil" con correo "pedro.gil@empresa.com", puesto "Operador", departamento "Operaciones" y fecha de ingreso "2099-01-01"
    Entonces el sistema responde 422 con el mensaje "La fecha de ingreso no puede ser futura"
    Y no se crea ningún empleado nuevo

  Escenario: Nombre demasiado corto
    Dado que no existe ningún empleado con correo "a.b@empresa.com"
    Cuando registro a "A" con correo "a.b@empresa.com", puesto "Analista", departamento "Tecnología" y fecha de ingreso "2024-03-15"
    Entonces el sistema responde 422 y la pantalla indica que debe corregirse el campo "nombre"
    Y no se crea ningún empleado nuevo

  Escenario: Puesto vacío
    Dado que no existe ningún empleado con correo "sofia.mena@empresa.com"
    Cuando registro a "Sofía Mena" con correo "sofia.mena@empresa.com", puesto vacío, departamento "Recursos Humanos" y fecha de ingreso "2024-03-15"
    Entonces el sistema responde 422 y la pantalla indica que debe corregirse el campo "puesto"
    Y no se crea ningún empleado nuevo

  Escenario: Departamento fuera de la lista permitida
    Dado que no existe ningún empleado con correo "raul.vega@empresa.com"
    Cuando registro a "Raúl Vega" con correo "raul.vega@empresa.com", puesto "Analista", departamento "Marketing" y fecha de ingreso "2024-03-15"
    Entonces el sistema responde 422 y la pantalla indica que debe corregirse el campo "departamento"
    Y no se crea ningún empleado nuevo

  Escenario: Fecha de ingreso ausente
    Dado que no existe ningún empleado con correo "eva.lara@empresa.com"
    Cuando registro a "Eva Lara" con correo "eva.lara@empresa.com", puesto "Analista", departamento "Ventas" y sin fecha de ingreso
    Entonces el sistema responde 422 y la pantalla indica que debe corregirse el campo "fecha_ingreso"
    Y no se crea ningún empleado nuevo

# Preguntas abiertas
# - ¿Se aceptan fechas de ingreso muy antiguas (por ejemplo 1950-01-01)? Las reglas solo prohíben fechas futuras.
# - ¿El número de empleado se consume si el registro falla por validación? Se asume que no.
# - ¿Se recortan espacios al inicio y al final de nombre y puesto antes de validar la longitud?
# - ¿Un empleado dado de baja conserva su correo reservado para la regla de unicidad? Se asume que sí.
