# Construit GTC_PREPARATION_JOURNALIERE.xlsm a partir du modele .xlsx et du module VBA.
# Prerequis : Microsoft Excel installe ; dans Excel > Options > Centre de gestion de la
# confidentialite > Parametres des macros : cocher "Acces approuve au modele d'objet du
# projet VBA" (peut etre decoche apres la construction).
# STATUT : non execute dans l'environnement de developpement (pas d'Excel) - a valider.
param(
  [string]$Modele = "$PSScriptRoot\GTC_PREPARATION_JOURNALIERE_modele.xlsx",
  [string]$Module = "$PSScriptRoot\GTC_Preparation.bas",
  [string]$Sortie = "$PSScriptRoot\GTC_PREPARATION_JOURNALIERE.xlsm"
)
$ErrorActionPreference = "Stop"
$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false
try {
  $wb = $excel.Workbooks.Open((Resolve-Path $Modele).Path)
  $null = $wb.VBProject.VBComponents.Import((Resolve-Path $Module).Path)
  $ws = $wb.Worksheets.Item("COLLAGE")
  $b1 = $ws.Buttons().Add(700, 5, 170, 28)
  $b1.Text = "Trier et preparer"
  $b1.OnAction = "TrierEtPreparer"
  $b2 = $ws.Buttons().Add(880, 5, 260, 28)
  $b2.Text = "Reinitialiser pour une nouvelle journee"
  $b2.OnAction = "ReinitialiserJournee"
  $wb.SaveAs($Sortie, 52)   # 52 = xlOpenXMLWorkbookMacroEnabled
  $wb.Close($false)
  Write-Host "Classeur macro cree : $Sortie"
} finally {
  $excel.Quit()
  [System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null
}
