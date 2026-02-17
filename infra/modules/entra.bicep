// infra/modules/entra.bicep

// Este módulo documenta la necesidad de registrar una aplicación en Entra ID
// La aplicación debe registrarse manualmente o mediante un script externo
// ya que Bicep tiene limitaciones para crear registros de aplicaciones de forma directa

// Outputs con valores predeterminados que deben actualizarse manualmente después del registro
output clientId string = ''
output tenantId string = subscription().tenantId
output objectId string = ''