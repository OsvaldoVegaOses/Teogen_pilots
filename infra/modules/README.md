Key Vault Module
=================

Uso:

- El módulo `keyvault.bicep` crea un Key Vault con RBAC activado y permite crear role assignments opcionales.
- Llamar desde un archivo padre (ej.: `infra/examples/deploy-keyvault.bicep`) pasando `vaultName`, `location` y opcionalmente `roleAssignments`.

Ejemplo de roleAssignments:

```
[
  {
    "principalId": "<principal-guid>",
    "roleDefinitionId": "<role-guid>",
    "principalType": "ServicePrincipal"
  }
]
```

Nota: Si los principalId no existen aún en la suscripción la asignación fallará; asegúrate de crear/obtener los SPs o managed identities primero.
