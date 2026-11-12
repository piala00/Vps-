Attribute VB_Name = "GTC_Preparation"
' =============================================================================
' GTC - Classeur de preparation journaliere (GTC_PREPARATION_JOURNALIERE.xlsm)
' Boutons : "Trier et preparer" (TrierEtPreparer) et
'           "Reinitialiser pour une nouvelle journee" (ReinitialiserJournee).
' Regles lues dans la feuille PARAMETRES (identiques a la configuration de
' l'application Python). La feuille COLLAGE n'est JAMAIS modifiee par le tri.
' STATUT : code NON EXECUTE dans l'environnement de developpement (pas d'Excel).
'          A tester sur Windows avant mise en production.
' Fichier source volontairement en ASCII pur (accents via ChrW).
' =============================================================================
Option Explicit

Private Const FORMAT_VERSION As String = "GTC-EXPORT-1"
Private Const ENTETE_EXPORT As String = "format_version|id_import|agence|date_rapport|type_mouvement|reference_piece|code_tiers|nom_client|acheteur_detail|montant|sens|bc_origine|mode_reference|source_feuille|source_ligne|empreinte_ligne"
Private Const ENTETE_MVT As String = "ct_num|client_libelle|nature|reference_piece|bc_origine|type_document|montant|sens|mode_reference|acheteur_detail|feuille|ligne|notes"
Private Const ENTETE_ANO As String = "feuille|ligne|section|gravite|motif|contenu|proposition|statut"

Private gTypes As Object        ' prefixe -> "NATURE|SENS"
Private gExclusions As Collection
Private gCollectifs As Collection
Private gEnteteRecus As String
Private gColsFacture As Variant
Private gColsBC As Variant
Private gColRecu As String
Private gVidesFin As Long
Private gAcompteCol As String
Private gBons As Collection
Private gAnnulees As Collection

' ----------------------------------------------------------------------------
Public Sub TrierEtPreparer()
    Dim wsC As Worksheet, wsP As Worksheet
    Dim dRap As Variant, agence As String
    Dim lastRow As Long, r As Long, idxRecus As Long
    Dim nFac As Long, nReg As Long, nAno As Long, nBC As Long, nTot As Long, nHors As Long, nAcpt As Long, nAnn As Long, nAnnR As Long
    On Error GoTo Erreur
    Set wsC = ThisWorkbook.Worksheets("COLLAGE")
    Set wsP = ThisWorkbook.Worksheets("PARAMETRES")
    ChargerRegles wsP
    dRap = Param(wsP, "DATE DU RAPPORT")
    agence = Trim$(CStr(Param(wsP, "AGENCE")))
    If Not IsDate(dRap) Then
        MsgBox "Renseigner la date du rapport dans PARAMETRES.", vbExclamation, "GTC"
        Exit Sub
    End If
    lastRow = DerniereLigne(wsC)
    If lastRow = 0 Then
        MsgBox "La feuille COLLAGE est vide : coller la feuille du jour.", vbExclamation, "GTC"
        Exit Sub
    End If
    Dim dFeuille As Variant, rr As Long, cc As Long
    For rr = 1 To 8
        For cc = 1 To 3
            If IsDate(wsC.Cells(rr, cc).Value) And VarType(wsC.Cells(rr, cc).Value) = vbDate Then dFeuille = wsC.Cells(rr, cc).Value: Exit For
        Next cc
        If Not IsEmpty(dFeuille) Then Exit For
    Next rr
    If Not IsEmpty(dFeuille) Then
        If CLng(CDate(dFeuille)) <> CLng(CDate(dRap)) Then
            MsgBox "La feuille collee est datee du " & Format(dFeuille, "dd/mm/yyyy") & " mais la date du rapport saisie est le " & _
                   Format(dRap, "dd/mm/yyyy") & "." & vbCrLf & "Verifier la journee collee.", vbCritical, "GTC"
            Exit Sub
        End If
    End If
    Application.ScreenUpdating = False
    Vider "FACTURES", ENTETE_MVT
    Vider "REGLEMENTS", ENTETE_MVT
    Vider "ANOMALIES", ENTETE_ANO
    Vider "EXPORT_ERP", ENTETE_EXPORT

    idxRecus = 0
    For r = 1 To lastRow
        If InStr(1, Norm(TexteLigne(wsC, r)), Norm(gEnteteRecus), vbBinaryCompare) > 0 Then
            idxRecus = r
            Exit For
        End If
    Next r
    If idxRecus = 0 Then
        Anomalie 0, "RECUS", "BLOQUANT", "Entete '" & gEnteteRecus & "' introuvable", "", "Verifier que la feuille complete a ete collee"
        nAno = nAno + 1
    End If

    ' ---- Section 1 : documents commerciaux ---------------------------------
    Dim fin1 As Long: fin1 = IIf(idxRecus = 0, lastRow, idxRecus - 1)
    Dim num As String, cli As String, pref As String, regle As String, nature As String, sens As String
    Dim mt As Variant, mts As Collection, i As Long, aMontant As Boolean, notes As String
    For r = 1 To fin1
        num = Txt(wsC, r, "C"): cli = Txt(wsC, r, "D")
        aMontant = False
        For i = LBound(gColsFacture) To UBound(gColsFacture)
            If EstMontant(wsC.Range(gColsFacture(i) & r).Value) Then aMontant = True
        Next i
        For i = LBound(gColsBC) To UBound(gColsBC)
            If EstMontant(wsC.Range(gColsBC(i) & r).Value) Then aMontant = True
        Next i
        If num = "" And cli = "" Then
            If aMontant Then nTot = nTot + 1
        ElseIf EstExclu(wsC, r) Then
            If InStr(Norm(TexteLigne(wsC, r)), "TOTAL") > 0 Then nTot = nTot + 1 Else nHors = nHors + 1
        ElseIf Not EstDocument(num) Then
            If aMontant Then Anomalie r, "DOCUMENTS", "AVERTISSEMENT", "Ligne avec montant mais numero de document non reconnu", TexteLigne(wsC, r), "Verifier la colonne C": nAno = nAno + 1
        Else
            Set mts = New Collection
            Dim ok As Boolean: ok = True
            For i = LBound(gColsFacture) To UBound(gColsFacture)
                mt = Montant(wsC.Range(gColsFacture(i) & r).Value, ok)
                If Not ok Then Exit For
                If Not IsEmpty(mt) Then If mt <> 0 Then mts.Add mt
            Next i
            Dim acpt As Variant: acpt = 0
            If ok And gAcompteCol <> "" Then
                acpt = Montant(wsC.Range(gAcompteCol & r).Value, ok)
                If IsEmpty(acpt) Then acpt = 0
            End If
            pref = Prefixe(num)
            If Not ok Then
                Anomalie r, "DOCUMENTS", "BLOQUANT", "Montant illisible", TexteLigne(wsC, r), "Corriger le montant": nAno = nAno + 1
            ElseIf EstDansListe(Norm(Txt(wsC, r, "E")), gAnnulees) Then
                If mts.Count > 0 Or acpt <> 0 Then
                    Anomalie r, "DOCUMENTS", "BLOQUANT", "Ligne marquee ANNULEE mais portant un montant", TexteLigne(wsC, r), "Verifier l'annulation": nAno = nAno + 1
                Else
                    nAnn = nAnn + 1
                End If
            ElseIf cli = "" Then
                If mts.Count > 0 Or acpt <> 0 Then Anomalie r, "DOCUMENTS", "BLOQUANT", "Client absent (colonne D)", TexteLigne(wsC, r), "Renseigner le client": nAno = nAno + 1
            Else
                If acpt <> 0 Then
                    ' Acompte encaisse a la commande : reglement du client
                    EcrireMvt "REGLEMENTS", agence, dRap, "ACOMPTE", num, cli, Abs(CDbl(acpt)), IIf(acpt > 0, "C", "D"), Txt(wsC, r, "B"), Txt(wsC, r, "E"), pref, r, "acompte"
                    nAcpt = nAcpt + 1
                End If
                If mts.Count = 0 Then
                    If gTypes.Exists(pref) Then
                        Anomalie r, "DOCUMENTS", "INFO", "Facture " & num & " sans montant", TexteLigne(wsC, r), "Aucun mouvement cree"
                    End If
                    nBC = nBC + 1                                   ' BC/BL seul : pas de creance
                ElseIf mts.Count > 1 And Not ToutesEgales(mts) Then
                    Anomalie r, "DOCUMENTS", "BLOQUANT", "Montants facture differents dans " & Join(gColsFacture, "/"), TexteLigne(wsC, r), "Determiner la colonne applicable": nAno = nAno + 1
                ElseIf EstDansListe(pref, gBons) Then
                    Anomalie r, "DOCUMENTS", "BLOQUANT", "Numero de bon (" & num & ") avec un montant de facture : numero de facture absent", TexteLigne(wsC, r), "Remplacer par le numero de la facture Sage": nAno = nAno + 1
                ElseIf Not gTypes.Exists(pref) Then
                    Anomalie r, "DOCUMENTS", "BLOQUANT", "Type de document '" & pref & "' non parametre", TexteLigne(wsC, r), "Parametrer le type (PARAMETRES)": nAno = nAno + 1
                Else
                    regle = gTypes(pref)
                    nature = Split(regle, "|")(0): sens = Split(regle, "|")(1)
                    mt = mts(1): notes = ""
                    If mt < 0 Then
                        mt = -mt
                        If nature <> "AVOIR" Then
                            nature = "AVOIR": sens = IIf(sens = "D", "C", "D"): notes = "montant negatif dans le rapport"
                        End If
                    End If
                    EcrireMvt "FACTURES", agence, dRap, nature, num, cli, CDbl(mt), sens, Txt(wsC, r, "B"), Txt(wsC, r, "E"), pref, r, notes
                    nFac = nFac + 1
                End If
            End If
        End If
    Next r

    ' ---- Section 2 : recus de versements ------------------------------------
    If idxRecus > 0 Then
        Dim vides As Long, okm As Boolean
        For r = idxRecus + 1 To lastRow
            If Trim$(TexteLigne(wsC, r)) = "" Then
                vides = vides + 1
                If vides >= gVidesFin Then Exit For
            Else
                vides = 0
                num = Txt(wsC, r, "C"): cli = Txt(wsC, r, "D")
                If EstEnteteSection(wsC, r) And Not EstRecu(num) Then Exit For
                If EstExclu(wsC, r) Then
                    If InStr(Norm(TexteLigne(wsC, r)), "TOTAL") > 0 Then nTot = nTot + 1 Else nHors = nHors + 1
                ElseIf Not EstRecu(num) Then
                    If EstMontant(wsC.Range(gColRecu & r).Value) Then Anomalie r, "RECUS", "AVERTISSEMENT", "Ligne avec montant sans reference de recu", TexteLigne(wsC, r), "Verifier s'il s'agit d'un reglement client": nAno = nAno + 1
                Else
                    okm = True
                    mt = Montant(wsC.Range(gColRecu & r).Value, okm)
                    If Not okm Then
                        Anomalie r, "RECUS", "BLOQUANT", "Montant illisible", TexteLigne(wsC, r), "Corriger le montant": nAno = nAno + 1
                    ElseIf IsEmpty(mt) Then
                        Anomalie r, "RECUS", "AVERTISSEMENT", "Recu sans montant", TexteLigne(wsC, r), "": nAno = nAno + 1
                    ElseIf mt = 0 Or cli = "" Then
                        Anomalie r, "RECUS", "BLOQUANT", "Recu nul ou sans client", TexteLigne(wsC, r), "Traitement manuel": nAno = nAno + 1
                    ElseIf mt < 0 Then
                        ' Recu negatif : contre-passation d'un recu fait sur un compte errone
                        EcrireMvt "REGLEMENTS", agence, dRap, "ANNULATION_RECU", num, cli, -CDbl(mt), "D", "", Txt(wsC, r, "E"), Prefixe(num), r, "annulation de recu (compte errone)"
                        nAnnR = nAnnR + 1
                    Else
                        EcrireMvt "REGLEMENTS", agence, dRap, "REGLEMENT", num, cli, CDbl(mt), "C", "", Txt(wsC, r, "E"), Prefixe(num), r, ""
                        nReg = nReg + 1
                    End If
                End If
            End If
        Next r
    End If
    FinaliserIdImport agence, dRap
    Application.ScreenUpdating = True
    ThisWorkbook.Worksheets("EXPORT_ERP").Activate
    MsgBox "Preparation terminee." & vbCrLf & _
           "Factures/avoirs : " & nFac & vbCrLf & "Acomptes : " & nAcpt & vbCrLf & "Reglements : " & nReg & vbCrLf & "Annulations de recus : " & nAnnR & vbCrLf & _
           "Lignes annulees : " & nAnn & vbCrLf & _
           "BC/BL seuls ignores : " & nBC & vbCrLf & "Totaux exclus : " & nTot & vbCrLf & _
           "Hors perimetre exclus : " & nHors & vbCrLf & "Anomalies : " & nAno & vbCrLf & vbCrLf & _
           "Les codes tiers Sage sont completes par l'application lors de l'import.", vbInformation, "GTC"
    Exit Sub
Erreur:
    Application.ScreenUpdating = True
    MsgBox "Erreur " & Err.Number & " : " & Err.Description, vbCritical, "GTC"
End Sub

' ----------------------------------------------------------------------------
Public Sub ReinitialiserJournee()
    Dim nExp As Long, rep As VbMsgBoxResult, nom As String, wsP As Worksheet
    Set wsP = ThisWorkbook.Worksheets("PARAMETRES")
    nExp = DerniereLigne(ThisWorkbook.Worksheets("EXPORT_ERP")) - 1
    If nExp > 0 Then
        rep = MsgBox(nExp & " ligne(s) presentes dans EXPORT_ERP." & vbCrLf & _
                     "Enregistrer une copie datee du classeur avant de vider ?", vbYesNoCancel + vbQuestion, "GTC")
        If rep = vbCancel Then Exit Sub
        If rep = vbYes Then
            nom = ThisWorkbook.Path & Application.PathSeparator & "GTC_PREPARATION_" & _
                  Format(Param(wsP, "DATE DU RAPPORT"), "yyyymmdd") & "_" & Format(Now, "hhnnss") & ".xlsm"
            ThisWorkbook.SaveCopyAs nom
            MsgBox "Copie enregistree : " & nom, vbInformation, "GTC"
        End If
    End If
    If MsgBox("Vider COLLAGE, FACTURES, REGLEMENTS, ANOMALIES et EXPORT_ERP pour une nouvelle journee ?", _
              vbYesNo + vbExclamation, "Confirmation") <> vbYes Then Exit Sub
    ThisWorkbook.Worksheets("COLLAGE").Cells.Clear
    Vider "FACTURES", ENTETE_MVT
    Vider "REGLEMENTS", ENTETE_MVT
    Vider "ANOMALIES", ENTETE_ANO
    Vider "EXPORT_ERP", ENTETE_EXPORT
    SetParam wsP, "DATE DU RAPPORT", ""
    ThisWorkbook.Worksheets("COLLAGE").Activate
End Sub

' ============================== utilitaires ==================================
Private Sub ChargerRegles(ws As Worksheet)
    Dim r As Long, k As String, last As Long
    Set gTypes = CreateObject("Scripting.Dictionary")
    Set gExclusions = New Collection
    Set gCollectifs = New Collection
    gEnteteRecus = "RECUS DE VERSEMENTS": gColRecu = "F": gVidesFin = 8
    gColsFacture = Array("H", "I"): gColsBC = Array("F", "G")
    gAcompteCol = ""
    Set gBons = New Collection
    Set gAnnulees = New Collection
    last = DerniereLigne(ws)
    For r = 1 To last
        k = UCase$(Trim$(CStr(ws.Cells(r, 1).Value)))
        Select Case k
            Case "TYPE_DOCUMENT": gTypes(UCase$(Trim$(ws.Cells(r, 2).Value))) = UCase$(Trim$(ws.Cells(r, 3).Value)) & "|" & UCase$(Trim$(ws.Cells(r, 4).Value))
            Case "EXCLUSION": gExclusions.Add Norm(CStr(ws.Cells(r, 2).Value))
            Case "COMPTE_COLLECTIF": gCollectifs.Add Norm(CStr(ws.Cells(r, 2).Value))
            Case "ENTETE_RECUS": gEnteteRecus = CStr(ws.Cells(r, 2).Value)
            Case "COLONNES_FACTURE": gColsFacture = Split(Replace(CStr(ws.Cells(r, 2).Value), " ", ""), ",")
            Case "COLONNES_BC": gColsBC = Split(Replace(CStr(ws.Cells(r, 2).Value), " ", ""), ",")
            Case "COLONNE_MONTANT_RECU": gColRecu = Trim$(CStr(ws.Cells(r, 2).Value))
            Case "LIGNES_VIDES_FIN_SECTION": gVidesFin = CLng(ws.Cells(r, 2).Value)
            Case "ACOMPTE_COLONNE": gAcompteCol = UCase$(Trim$(CStr(ws.Cells(r, 2).Value)))
            Case "PREFIXE_BON": gBons.Add UCase$(Trim$(CStr(ws.Cells(r, 2).Value)))
            Case "VALEUR_ANNULEE": gAnnulees.Add Norm(CStr(ws.Cells(r, 2).Value))
        End Select
    Next r
End Sub

Private Function Param(ws As Worksheet, cle As String) As Variant
    Dim r As Long
    For r = 1 To DerniereLigne(ws)
        If UCase$(Trim$(CStr(ws.Cells(r, 1).Value))) = cle Then Param = ws.Cells(r, 2).Value: Exit Function
    Next r
    Param = Empty
End Function

Private Sub SetParam(ws As Worksheet, cle As String, v As Variant)
    Dim r As Long
    For r = 1 To DerniereLigne(ws)
        If UCase$(Trim$(CStr(ws.Cells(r, 1).Value))) = cle Then ws.Cells(r, 2).Value = v: Exit Sub
    Next r
End Sub

Private Function DerniereLigne(ws As Worksheet) As Long
    Dim c As Range
    Set c = ws.Cells.Find(What:="*", LookIn:=xlValues, SearchOrder:=xlByRows, SearchDirection:=xlPrevious)
    If c Is Nothing Then DerniereLigne = 0 Else DerniereLigne = c.Row
End Function

Private Sub Vider(nom As String, entete As String)
    Dim ws As Worksheet, h As Variant, i As Long
    Set ws = ThisWorkbook.Worksheets(nom)
    ws.Cells.Clear
    h = Split(entete, "|")
    For i = 0 To UBound(h)
        ws.Cells(1, i + 1).Value = h(i)
    Next i
    ws.Rows(1).Font.Bold = True
    If nom = "EXPORT_ERP" Then
        ' colonnes texte : id, date ISO, references (evite les conversions automatiques d'Excel)
        ws.Range("B:B,D:D,F:F,G:G,L:L").NumberFormat = "@"
    End If
End Sub

Private Function Txt(ws As Worksheet, r As Long, col As String) As String
    Dim v As Variant: v = ws.Range(col & r).Value
    If IsError(v) Or IsEmpty(v) Then Txt = "" Else Txt = Trim$(CStr(v))
End Function

Private Function TexteLigne(ws As Worksheet, r As Long) As String
    Dim c As Long, s As String, v As Variant
    For c = 1 To 12
        v = ws.Cells(r, c).Value
        If Not IsError(v) Then If Trim$(CStr(v)) <> "" Then s = s & " " & Trim$(CStr(v))
    Next c
    TexteLigne = Trim$(s)
End Function

Private Function Norm(ByVal s As String) As String
    ' Majuscules sans accents, espaces compactes
    Dim a As Variant, b As Variant, i As Long
    s = UCase$(s)
    a = Array(192, 193, 194, 195, 196, 199, 200, 201, 202, 203, 204, 205, 206, 207, 210, 211, 212, 214, 217, 218, 219, 220, 160)
    b = Array("A", "A", "A", "A", "A", "C", "E", "E", "E", "E", "I", "I", "I", "I", "O", "O", "O", "O", "U", "U", "U", "U", " ")
    For i = 0 To UBound(a)
        s = Replace(s, ChrW(a(i)), b(i))
    Next i
    Do While InStr(s, "  ") > 0: s = Replace(s, "  ", " "): Loop
    Norm = Trim$(s)
End Function

Private Function Compacte(ByVal s As String) As String
    Dim i As Long, ch As String, o As String
    s = Norm(s)
    For i = 1 To Len(s)
        ch = Mid$(s, i, 1)
        If ch Like "[A-Z0-9]" Then o = o & ch
    Next i
    Compacte = o
End Function

Private Function Prefixe(ByVal ref As String) As String
    ' "7RCB045" -> "RCB" ; "FACB 0123" -> "FACB"
    Dim s As String, i As Long, o As String
    s = Compacte(ref)
    i = 1
    Do While i <= Len(s) And Mid$(s, i, 1) Like "#": i = i + 1: Loop
    Do While i <= Len(s) And Mid$(s, i, 1) Like "[A-Z]": o = o & Mid$(s, i, 1): i = i + 1: Loop
    Prefixe = o
End Function

Private Function EstDocument(ByVal ref As String) As Boolean
    ' chiffres optionnels + 2 a 5 lettres + chiffres
    Dim s As String, p As String, reste As String
    s = Compacte(ref): p = Prefixe(ref)
    If Len(p) < 2 Or Len(p) > 5 Then Exit Function
    reste = Mid$(s, InStr(s, p) + Len(p))
    EstDocument = (Len(reste) > 0 And Left$(reste, 1) Like "#")
End Function

Private Function EstRecu(ByVal ref As String) As Boolean
    EstRecu = (Prefixe(ref) = "RCB" And EstDocument(ref))
End Function

Private Function EstExclu(ws As Worksheet, r As Long) As Boolean
    Dim t As String, m As Variant
    t = " " & Norm(Txt(ws, r, "B") & " " & Txt(ws, r, "C") & " " & Txt(ws, r, "D") & " " & Txt(ws, r, "E")) & " "
    t = Replace(Replace(Replace(t, ".", " "), ",", " "), ":", " ")
    For Each m In gExclusions
        If InStr(t, " " & m & " ") > 0 Then EstExclu = True: Exit Function
    Next m
End Function

Private Function EstEnteteSection(ws As Worksheet, r As Long) As Boolean
    Dim c As Long, n As Long, v As String, s As String
    For c = 1 To 12
        If Not IsError(ws.Cells(r, c).Value) Then
            v = Trim$(CStr(ws.Cells(r, c).Value))
            If v <> "" Then n = n + 1: s = v
        End If
    Next c
    If n <> 1 Or Len(s) < 6 Then Exit Function
    If s <> UCase$(s) Then Exit Function
    If s Like "*#*" Then Exit Function
    EstEnteteSection = True
End Function

Private Function Montant(ByVal v As Variant, ByRef ok As Boolean) As Variant
    ' Retourne Empty si vide ; ok=False si illisible ou avec centimes
    Dim s As String, neg As Boolean, i As Long
    ok = True
    If IsError(v) Then ok = False: Exit Function
    If IsEmpty(v) Then Montant = Empty: Exit Function
    If IsNumeric(v) And VarType(v) <> vbString Then
        If Abs(v - Round(v, 0)) >= 0.01 Then ok = False: Exit Function
        Montant = Round(v, 0): Exit Function
    End If
    s = UCase$(Trim$(CStr(v)))
    If s = "" Or s = "-" Then Montant = Empty: Exit Function
    If Left$(s, 1) = "(" And Right$(s, 1) = ")" Then neg = True: s = Mid$(s, 2, Len(s) - 2)
    s = Replace(s, "FCFA", ""): s = Replace(s, "XAF", "")
    s = Replace(s, " ", ""): s = Replace(s, ChrW(160), ""): s = Replace(s, ChrW(8239), "")
    If InStr(s, ",") > 0 Then ok = False: Exit Function            ' decimale : a verifier manuellement
    If InStr(s, ".") > 0 Then
        If Not (s Like "#*.###" And Len(s) - InStrRev(s, ".") = 3) Then ok = False: Exit Function
        s = Replace(s, ".", "")                                       ' separateur de milliers
    End If
    If Left$(s, 1) = "-" Then neg = Not neg: s = Mid$(s, 2)
    If Len(s) = 0 Then ok = False: Exit Function
    For i = 1 To Len(s)
        If Not Mid$(s, i, 1) Like "#" Then ok = False: Exit Function
    Next i
    Montant = CDbl(s) * IIf(neg, -1, 1)
End Function

Private Function EstMontant(ByVal v As Variant) As Boolean
    Dim ok As Boolean, m As Variant
    m = Montant(v, ok)
    If Not ok Then
        EstMontant = (CStr(v) Like "*#*")
    ElseIf Not IsEmpty(m) Then
        EstMontant = (m <> 0)
    End If
End Function

Private Function ToutesEgales(c As Collection) As Boolean
    Dim i As Long
    ToutesEgales = True
    For i = 2 To c.Count
        If c(i) <> c(1) Then ToutesEgales = False: Exit Function
    Next i
End Function

Private Function EstDansListe(v As String, c As Collection) As Boolean
    Dim m As Variant
    For Each m In c
        If v = m Then EstDansListe = True: Exit Function
    Next m
End Function

Private Function EstCollectif(cli As String) As Boolean
    Dim m As Variant
    For Each m In gCollectifs
        If Norm(cli) = m Then EstCollectif = True: Exit Function
    Next m
End Function

Private Sub Anomalie(r As Long, section As String, gravite As String, motif As String, contenu As String, proposition As String)
    Dim ws As Worksheet, n As Long
    Set ws = ThisWorkbook.Worksheets("ANOMALIES")
    n = DerniereLigne(ws) + 1
    ws.Range("A" & n).Resize(1, 8).Value = Array("COLLAGE", r, section, gravite, motif, Left$(contenu, 250), proposition, "OUVERTE")
End Sub

Private Sub EcrireMvt(feuille As String, agence As String, dRap As Variant, nature As String, num As String, _
                      cli As String, mt As Double, sens As String, bc As String, modeRef As String, _
                      pref As String, r As Long, notes As String)
    Dim ws As Worksheet, we As Worksheet, n As Long, ach As String
    If EstCollectif(cli) Then ach = modeRef
    Set ws = ThisWorkbook.Worksheets(feuille)
    n = DerniereLigne(ws) + 1
    ws.Range("A" & n).Resize(1, 13).Value = Array("", cli, nature, num, bc, pref, mt, sens, modeRef, ach, "COLLAGE", r, notes)
    Set we = ThisWorkbook.Worksheets("EXPORT_ERP")
    n = DerniereLigne(we) + 1
    we.Range("A" & n).Resize(1, 16).Value = Array(FORMAT_VERSION, "", agence, Format(dRap, "yyyy-mm-dd"), nature, num, "", _
        cli, ach, mt, sens, bc, modeRef, "COLLAGE", r, nature & "|" & Compacte(num) & "|" & Compacte(cli) & "|" & mt & "|" & sens)
End Sub

Private Sub FinaliserIdImport(agence As String, dRap As Variant)
    ' Identifiant de lot : agence-date-nombre-somme-controle (l'unicite metier est
    ' de toute facon garantie ligne par ligne par l'application).
    Dim we As Worksheet, n As Long, r As Long, somme As Double, ctl As Double, id As String
    Set we = ThisWorkbook.Worksheets("EXPORT_ERP")
    n = DerniereLigne(we)
    For r = 2 To n
        somme = somme + we.Cells(r, 10).Value
        ctl = ctl + (r - 1) * (we.Cells(r, 10).Value - 9973# * Int(we.Cells(r, 10).Value / 9973#)) + Len(we.Cells(r, 6).Value) * 31
    Next r
    id = agence & "-" & Format(dRap, "yyyy-mm-dd") & "-V" & (n - 1) & "-" & Format(somme, "0") & "-" & Format(ctl, "0")
    For r = 2 To n
        we.Cells(r, 2).Value = id
    Next r
End Sub
